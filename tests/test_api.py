from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from support import (
    TEST_MODEL,
    WRITE_FILE_CANDIDATES,
    FakeJev,
    StubResolver,
    eval_run,
    route_answers,
    verify_answers,
)

from apps.api.app import create_app, default_registry
from apps.api.config import Settings
from apps.api.storage import TraceStore
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.clients.llm import LLMClientConfig, LLMCompletion, LLMHttpError
from jev_router.tools import CalculatorTool, ToolRegistry, WriteFileTool

TERMINAL = frozenset(
    {
        "completed",
        "needs_user_input",
        "needs_confirmation",
        "rejected",
        "budget_exhausted",
        "failed",
    }
)

SECRET = "sk-live-should-never-be-returned"
AWAITING_CONFIRMATION = frozenset({"awaiting_confirmation"})
AWAITING_INPUT = frozenset({"awaiting_input"})


@pytest.fixture
def api(tmp_path: Path):
    created: list[TraceStore] = []

    def make(
        fake: FakeJev,
        *,
        tools: ToolRegistry | None = None,
        resolver: Any = None,
        llm_client: Any = None,
        stub_resolver: bool = True,
        **settings: Any,
    ) -> TestClient:
        resolved = Settings(
            model=TEST_MODEL,
            database_path=str(tmp_path / f"traces-{len(created)}.db"),
            workspace_root=str(tmp_path / f"workspace-{len(created)}"),
            jev=JevClientConfig(api_key=SECRET),
            **settings,
        )
        store = TraceStore(resolved.database_path)
        created.append(store)
        app = create_app(
            resolved,
            store=store,
            tools=tools if tools is not None else ToolRegistry([CalculatorTool()]),
            resolver=(
                resolver
                if resolver is not None
                else (StubResolver() if stub_resolver else None)
            ),
            client=JevClient(resolved.jev, fake.transport()),
            llm_client=llm_client,
        )
        return TestClient(app)

    yield make
    for store in created:
        store.close()


def wait_for(
    client: TestClient, task_id: str, statuses: frozenset[str], timeout: float = 5.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/tasks/{task_id}").json()
        if body["status"] in statuses:
            return body
        time.sleep(0.005)
    raise AssertionError(f"run {task_id} never reached {sorted(statuses)}")


def wait_for_terminal(client: TestClient, task_id: str) -> dict[str, Any]:
    return wait_for(client, task_id, TERMINAL)


def submit(client: TestClient, goal: str = "Calculate 2 + 2") -> str:
    response = client.post("/tasks", json={"goal": goal})
    assert response.status_code == 202
    return response.json()["task_id"]


def test_submitting_a_task_is_accepted(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["task_id"] == task_id
    assert body["status"] == "completed"
    assert body["goal"] == "Calculate 2 + 2"
    assert body["step"] == 1
    assert body["diagnostic"] is None
    assert body["pending_confirmation"] is None


def test_traces_are_served_for_a_finished_run(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        task_id = submit(client)
        wait_for_terminal(client, task_id)
        response = client.get(f"/tasks/{task_id}/traces")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert len(payload["traces"]) == 1
    trace = payload["traces"][0]
    assert trace["action"] == "calculator"
    assert trace["policy_outcome"] == "execute"
    assert trace["executed"] is True
    assert trace["result"] == {"result": 4.0}
    assert trace["completion_probability"] == 0.82
    assert trace["quality_score"] == 3.0
    assert trace["route_confidence"] == 0.9
    assert trace["duration_ms"] >= 0


def test_traces_are_served_while_the_run_is_still_going(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("ask_user"))

    with api(fake) as client:
        task_id = submit(client, "Find the weather in Tokyo")
        body = wait_for(client, task_id, AWAITING_INPUT)

        assert body["status"] == "awaiting_input"
        response = client.get(f"/tasks/{task_id}/traces")

    assert response.status_code == 200
    # The blocked step has not completed, so the Runner has not emitted its trace
    # yet; what is pending is reported by the task itself.
    assert response.json()["traces"] == []
    assert body["pending_input"] == {"question": "ask_user", "step": 0}


def test_an_unknown_task_is_not_found(api: Any) -> None:
    fake = FakeJev()
    with api(fake) as client:
        assert client.get("/tasks/missing").status_code == 404
        assert client.get("/tasks/missing/traces").status_code == 404
        assert client.post("/tasks/missing/confirm", json={"approved": True}).status_code == 404
        assert client.post("/tasks/missing/input", json={"answer": "Tokyo"}).status_code == 404


def test_an_empty_goal_is_rejected(api: Any) -> None:
    fake = FakeJev()
    with api(fake) as client:
        assert client.post("/tasks", json={"goal": ""}).status_code == 422
        assert client.post("/tasks", json={"goal": "   "}).status_code == 422
        assert client.post("/tasks", json={}).status_code == 422


def test_unknown_fields_are_rejected(api: Any) -> None:
    fake = FakeJev()
    with api(fake) as client:
        assert client.post("/tasks", json={"goal": "x", "nope": 1}).status_code == 422
        assert client.post("/tasks/x/confirm", json={"approved": True, "nope": 1}).status_code == 422


def test_a_write_tool_waits_for_confirmation_with_its_arguments(api: Any, tmp_path: Path) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("write_file", WRITE_FILE_CANDIDATES))
    fake.verifies.append(verify_answers(0.82))
    arguments = {"path": "note.txt", "content": "hello"}

    workspace = tmp_path / "workspace-0"
    with api(
        fake,
        tools=ToolRegistry([WriteFileTool(workspace)]),
        resolver=StubResolver(arguments),
    ) as client:
        task_id = submit(client, "Write a note")
        body = wait_for(client, task_id, AWAITING_CONFIRMATION)

        assert body["status"] == "awaiting_confirmation"
        pending = body["pending_confirmation"]
        assert pending is not None
        assert pending["action"] == "write_file"
        assert pending["arguments"] == arguments
        assert pending["step"] == 0
        assert not (tmp_path / "workspace-0" / "note.txt").exists()

        approved = client.post(f"/tasks/{task_id}/confirm", json={"approved": True})
        assert approved.status_code == 204
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "completed"
    assert (tmp_path / "workspace-0" / "note.txt").read_text() == "hello"


def test_denied_confirmation_stops_the_run(api: Any, tmp_path: Path) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("write_file", WRITE_FILE_CANDIDATES))

    workspace = tmp_path / "workspace-0"
    with api(
        fake,
        tools=ToolRegistry([WriteFileTool(workspace)]),
        resolver=StubResolver({"path": "a.txt", "content": "x"}),
    ) as client:
        task_id = submit(client, "Write a file")
        wait_for(client, task_id, AWAITING_CONFIRMATION)
        client.post(f"/tasks/{task_id}/confirm", json={"approved": False})
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "needs_confirmation"
    assert not (tmp_path / "workspace-0" / "a.txt").exists()


def test_confirming_with_nothing_pending_conflicts(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        task_id = submit(client)
        wait_for_terminal(client, task_id)
        response = client.post(f"/tasks/{task_id}/confirm", json={"approved": True})

    assert response.status_code == 409


def test_ask_user_waits_for_input_then_continues(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("ask_user"))
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        task_id = submit(client, "Find the weather")
        body = wait_for(client, task_id, AWAITING_INPUT)

        assert body["status"] == "awaiting_input"
        assert body["pending_input"] == {"question": "ask_user", "step": 0}

        answered = client.post(f"/tasks/{task_id}/input", json={"answer": "Tokyo"})
        assert answered.status_code == 204
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "completed"
    assert body["step"] == 2
    assert fake.route_calls() == 2


def test_providing_input_with_nothing_pending_conflicts(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        task_id = submit(client)
        wait_for_terminal(client, task_id)
        response = client.post(f"/tasks/{task_id}/input", json={"answer": "Tokyo"})

    assert response.status_code == 409


def test_an_empty_answer_is_rejected(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("ask_user"))

    with api(fake) as client:
        task_id = submit(client, "Find the weather")
        wait_for(client, task_id, AWAITING_INPUT)
        assert client.post(f"/tasks/{task_id}/input", json={"answer": ""}).status_code == 422


def test_listing_tasks(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        first = submit(client, "First goal")
        second = submit(client, "Second goal")
        wait_for_terminal(client, first)
        wait_for_terminal(client, second)

        response = client.get("/tasks")
        assert response.status_code == 200
        listed = response.json()["tasks"]
        assert [task["task_id"] for task in listed] == [second, first]
        assert listed[0]["goal"] == "Second goal"

        assert client.get("/tasks?limit=1").json()["tasks"][0]["task_id"] == second
        assert client.get("/tasks?limit=0").status_code == 400


def test_the_credential_never_appears_in_a_response(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake) as client:
        task_id = submit(client)
        wait_for_terminal(client, task_id)
        bodies = [
            client.get("/tasks").text,
            client.get(f"/tasks/{task_id}").text,
            client.get(f"/tasks/{task_id}/traces").text,
        ]

    assert SECRET not in "".join(bodies)


def test_settings_require_a_model() -> None:
    with pytest.raises(ValueError, match="JEV_MODEL"):
        Settings.from_env({"JEV_API_KEY": "k"})


def test_settings_reject_a_budget_that_cannot_route_and_verify(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_model_calls"):
        Settings(
            model=TEST_MODEL,
            database_path=str(tmp_path / "traces.db"),
            jev=JevClientConfig(api_key="k"),
            max_steps=4,
            max_model_calls=4,
        )


def test_settings_read_the_environment(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "JEV_API_KEY": "k",
            "JEV_MODEL": "jev-latest",
            "JEV_DATABASE_PATH": str(tmp_path / "traces.db"),
            "JEV_MAX_STEPS": "3",
            "JEV_COMPLETION_THRESHOLD": "0.9",
        }
    )

    assert settings.model == "jev-latest"
    assert settings.max_steps == 3
    assert settings.max_model_calls == 16
    assert settings.completion_threshold == 0.9
    assert settings.budget().max_steps == 3


def test_settings_reject_a_non_numeric_threshold(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="JEV_COMPLETION_THRESHOLD"):
        Settings.from_env(
            {
                "JEV_API_KEY": "k",
                "JEV_MODEL": "m",
                "JEV_COMPLETION_THRESHOLD": "high",
            }
        )


def test_the_default_registry_omits_the_search_tools(tmp_path: Path) -> None:
    settings = Settings(
        model=TEST_MODEL,
        database_path=str(tmp_path / "traces.db"),
        jev=JevClientConfig(api_key="k"),
    )

    registry = default_registry(settings)

    assert registry.names() == ("calculator", "write_file", "send_mock_email")
    assert registry.get("write_file").risk == "write"


class StubLLM:
    """Stands in for the configured LLM behind delegation."""

    def __init__(self, text: str = "the reasoned answer") -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int | None = ...
    ) -> Any:
        self.calls.append({"model": model, "system": system, "prompt": prompt})
        return LLMCompletion(
            text=self.text, model="stub-llm", input_tokens=120, output_tokens=24
        )


def llm_settings(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "llm_model": "claude-sonnet-4-5",
        "llm": LLMClientConfig(api_key="llm-test-key"),
    }
    values.update(overrides)
    return values


def delegating_route() -> dict[str, Any]:
    # needs_reasoning above the 0.70 threshold routes to delegation.
    return route_answers("calculator", needs_reasoning=0.9)


def test_settings_leave_the_llm_unconfigured_by_default(tmp_path: Path) -> None:
    settings = Settings.from_env({"JEV_API_KEY": "k", "JEV_MODEL": "m"})

    assert settings.llm is None
    assert settings.llm_model is None


def test_settings_read_the_llm_environment(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "JEV_API_KEY": "k",
            "JEV_MODEL": "m",
            "LLM_API_KEY": "lk",
            "LLM_MODEL": "claude-sonnet-4-5",
        }
    )

    assert settings.llm is not None
    assert settings.llm_model == "claude-sonnet-4-5"


def test_settings_reject_an_llm_model_without_a_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        Settings.from_env({"JEV_API_KEY": "k", "JEV_MODEL": "m", "LLM_MODEL": "m2"})


def test_settings_reject_an_llm_key_without_a_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LLM_MODEL"):
        Settings.from_env({"JEV_API_KEY": "k", "JEV_MODEL": "m", "LLM_API_KEY": "lk"})


def test_settings_reject_a_half_configured_llm(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="together"):
        Settings(
            model=TEST_MODEL,
            database_path=str(tmp_path / "traces.db"),
            jev=JevClientConfig(api_key="k"),
            llm=LLMClientConfig(api_key="lk"),
        )


def test_a_delegating_run_uses_the_configured_llm(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(delegating_route())
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))
    llm = StubLLM()

    with api(fake, llm_client=llm, **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)
        traces = client.get(f"/tasks/{task_id}/traces").json()["traces"]

    assert body["status"] == "completed"
    assert body["step"] == 2
    assert [trace["policy_outcome"] for trace in traces] == ["delegate_to_llm", "execute"]
    assert traces[0]["action"] == "calculator"
    assert traces[0]["result"] == "the reasoned answer"
    assert traces[0]["executed"] is False
    assert traces[1]["executed"] is True
    assert llm.calls[0]["model"] == "claude-sonnet-4-5"
    assert "Calculate 2 + 2" in llm.calls[0]["prompt"]


def test_a_delegating_run_fails_closed_without_an_llm(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(delegating_route())

    with api(fake) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "failed"
    assert body["diagnostic"] == "delegation was requested but no handler is configured"


def test_a_failing_delegation_fails_the_run_with_its_category(api: Any) -> None:
    class BrokenLLM:
        async def complete(self, **kwargs: Any) -> Any:
            raise LLMHttpError(429)

    fake = FakeJev()
    fake.routes.append(delegating_route())

    with api(fake, llm_client=BrokenLLM(), **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "failed"
    assert "http" in (body["diagnostic"] or "")


def test_an_empty_delegation_fails_the_run(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(delegating_route())

    with api(fake, llm_client=StubLLM("   "), **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "failed"
    assert body["diagnostic"] is not None


def test_recording_an_eval_run_round_trips_through_the_api(api: Any) -> None:
    request = eval_run()

    with api(FakeJev()) as client:
        posted = client.post("/evals", json=request.model_dump(mode="json"))
        assert posted.status_code == 201
        assert posted.json() == {"run_id": "run-1", "case_count": 2}

        listed = client.get("/evals").json()
        assert listed["runs"] == [
            {
                "run_id": "run-1",
                "mode": "compare",
                "created_at": "2026-09-24T00:00:00+00:00",
                "case_count": 2,
            }
        ]

        detail = client.get("/evals/run-1").json()

    assert detail["run_id"] == "run-1"
    assert detail["case_count"] == 2
    assert detail["metrics"]["agreement_rate"] == 0.0
    assert detail["metrics"]["jev"]["expected_match_rate"] == 1.0
    assert [(o["case_id"], o["mode"]) for o in detail["outcomes"]] == [
        ("case-1", "jev"),
        ("case-1", "llm"),
        ("case-2", "jev"),
        ("case-2", "llm"),
    ]


def test_recording_the_same_eval_run_twice_is_idempotent(api: Any) -> None:
    with api(FakeJev()) as client:
        first = client.post("/evals", json=eval_run().model_dump(mode="json"))
        second = client.post("/evals", json=eval_run().model_dump(mode="json"))
        listed = client.get("/evals").json()

    assert first.status_code == second.status_code == 201
    assert len(listed["runs"]) == 1


def test_an_unknown_eval_run_is_not_found(api: Any) -> None:
    with api(FakeJev()) as client:
        response = client.get("/evals/nope")

    assert response.status_code == 404
    assert response.json()["detail"] == "eval run not found"


def test_an_eval_limit_below_one_is_rejected(api: Any) -> None:
    with api(FakeJev()) as client:
        response = client.get("/evals?limit=0")

    assert response.status_code == 400


def test_an_unknown_eval_mode_is_rejected(api: Any) -> None:
    body = eval_run().model_dump(mode="json")
    body["mode"] = "telepathy"

    with api(FakeJev()) as client:
        response = client.post("/evals", json=body)

    assert response.status_code == 422


def test_outcomes_from_another_router_are_rejected(api: Any) -> None:
    body = eval_run(mode="jev").model_dump(mode="json")
    body["outcomes"] = [o for o in body["outcomes"] if o["mode"] == "llm"]

    with api(FakeJev()) as client:
        response = client.post("/evals", json=body)

    assert response.status_code == 422


def test_an_unpaired_compare_run_is_rejected(api: Any) -> None:
    body = eval_run().model_dump(mode="json")
    # The baseline never answered case-2, so the pairing is broken.
    body["outcomes"] = [
        o for o in body["outcomes"] if not (o["case_id"] == "case-2" and o["mode"] == "llm")
    ]

    with api(FakeJev()) as client:
        response = client.post("/evals", json=body)

    assert response.status_code == 422


def test_an_eval_body_with_unknown_fields_is_rejected(api: Any) -> None:
    body = eval_run().model_dump(mode="json")
    body["surprise"] = True

    with api(FakeJev()) as client:
        response = client.post("/evals", json=body)

    assert response.status_code == 422


def test_an_empty_outcome_list_is_rejected(api: Any) -> None:
    body = eval_run().model_dump(mode="json")
    body["outcomes"] = []

    with api(FakeJev()) as client:
        response = client.post("/evals", json=body)

    assert response.status_code == 422


def test_a_run_executes_with_llm_synthesized_arguments(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))
    llm = StubLLM('{"expression": "6 * 7"}')

    with api(fake, llm_client=llm, stub_resolver=False, **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)
        traces = client.get(f"/tasks/{task_id}/traces").json()["traces"]

    assert body["status"] == "completed"
    assert traces[0]["executed"] is True
    assert traces[0]["arguments"] == {"expression": "6 * 7"}
    assert traces[0]["result"] == {"result": 42.0}
    assert llm.calls[0]["model"] == "claude-sonnet-4-5"
    assert "Calculate 2 + 2" in llm.calls[0]["prompt"]
    assert "- expression (string, required)" in llm.calls[0]["prompt"]


def test_a_failed_synthesis_stops_the_run_with_its_cause(api: Any) -> None:
    class BrokenLLM:
        async def complete(self, **kwargs: Any) -> Any:
            raise LLMHttpError(429)

    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    with api(fake, llm_client=BrokenLLM(), stub_resolver=False, **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "failed"
    assert "argument synthesis failed: http" in (body["diagnostic"] or "")


def test_a_malformed_synthesis_stops_the_run(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    with api(fake, llm_client=StubLLM("I would compute 6 * 7."), stub_resolver=False, **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "failed"
    assert "JSON object" in (body["diagnostic"] or "")


def test_arguments_the_tool_refuses_stop_the_run(api: Any) -> None:
    """The resolver returns the model's object unchanged; the tool decides."""
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    with api(fake, llm_client=StubLLM('{"expression": "import os"}'), stub_resolver=False, **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)
        traces = client.get(f"/tasks/{task_id}/traces").json()["traces"]

    assert body["status"] == "failed"
    assert "rejected its input" in (body["diagnostic"] or "")
    assert traces[0]["arguments"] == {"expression": "import os"}


def test_an_unconfigured_service_still_fails_closed_on_a_tool_call(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    with api(fake, stub_resolver=False) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)

    assert body["status"] == "failed"
    assert "rejected its input" in (body["diagnostic"] or "")


def test_an_injected_resolver_still_wins_over_the_llm_one(api: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    with api(fake, llm_client=StubLLM('{"expression": "6 * 7"}'), **llm_settings()) as client:
        task_id = submit(client)
        body = wait_for_terminal(client, task_id)
        traces = client.get(f"/tasks/{task_id}/traces").json()["traces"]

    assert body["status"] == "completed"
    # The injected stub answers 2 + 2, so the LLM's arguments were not used.
    assert traces[0]["arguments"] == {"expression": "2 + 2"}
    assert traces[0]["result"] == {"result": 4.0}
