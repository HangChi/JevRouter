from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import httpx
import pytest
from support import (
    EMAIL_CANDIDATES,
    OPAQUE_CANDIDATES,
    TEST_MODEL,
    WRITE_FILE_CANDIDATES,
    FakeJev,
    StubResolver,
    route_answers,
    verify_answers,
)

from jev_router.clients.jev import JevClient, JevClientConfig, NoulQuestion, TransportError
from jev_router.runner import (
    DEFAULT_COMPLETION_THRESHOLD,
    Runner,
    StepTrace,
)
from jev_router.state import ExecutionBudget, TaskState
from jev_router.tools.base import ToolResult
from jev_router.tools.calculator import CalculatorTool
from jev_router.tools.mock_email import MockEmailTool
from jev_router.tools.registry import ToolRegistry
from jev_router.tools.write_file import WriteFileTool


class StubConfirmation:
    def __init__(self, approved: bool = True) -> None:
        self.approved = approved
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def confirm(
        self, task_id: str, action: str, arguments: Any, state: TaskState
    ) -> bool:
        self.calls.append((task_id, action, dict(arguments)))
        return self.approved


class StubUserInput:
    def __init__(self, answer: str | None = "Tokyo") -> None:
        self.answer = answer
        self.calls: list[str] = []

    async def request_input(self, question: str, state: TaskState) -> str | None:
        self.calls.append(question)
        return self.answer


class StubDelegate:
    def __init__(self, answer: str | None = "The answer is 4.") -> None:
        self.answer = answer
        self.calls: list[TaskState] = []

    async def delegate(self, state: TaskState) -> str | None:
        self.calls.append(state)
        return self.answer


class ShrinkingRegistry(ToolRegistry):
    """Serves tool metadata for routing, then reports the tool gone at execution."""

    def __init__(self, tools: Any = ()) -> None:
        super().__init__(tools)
        self._metadata_served = False

    def get(self, name: str) -> Any:
        if self._metadata_served:
            raise KeyError("tool is not registered")
        self._metadata_served = True
        return super().get(name)


class OpaqueTool:
    name = "opaque"
    description = "Returns an output the state snapshot cannot hold."
    risk = "read"

    def execute(self, input: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, output={"value": object()})


class RecordingSink:
    def __init__(self) -> None:
        self.traces: list[StepTrace] = []

    def emit(self, trace: StepTrace) -> None:
        self.traces.append(trace)


class BrokenSink:
    def emit(self, trace: StepTrace) -> None:
        raise RuntimeError("sink is unavailable")


def build(
    fake: FakeJev,
    *,
    tools: ToolRegistry | None = None,
    budget: ExecutionBudget | None = None,
    resolver: Any = None,
    confirmation: Any = None,
    user_input: Any = None,
    delegate: Any = None,
    trace_sink: Any = None,
    completion_threshold: float = DEFAULT_COMPLETION_THRESHOLD,
) -> Runner:
    return Runner(
        client=JevClient(JevClientConfig(api_key="test-key"), fake.transport()),
        model=TEST_MODEL,
        tools=tools if tools is not None else ToolRegistry([CalculatorTool()]),
        budget=budget or ExecutionBudget(max_steps=4, max_model_calls=8),
        completion_threshold=completion_threshold,
        resolver=resolver,
        confirmation=confirmation,
        user_input=user_input,
        delegate=delegate,
        trace_sink=trace_sink,
    )


@pytest.mark.asyncio
async def test_single_execution_completes_when_verifier_passes() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "completed"
    assert result.diagnostic is None
    assert result.state.step == 1
    assert result.state.history[0].action == "calculator"
    assert result.state.last_result == {"result": 4.0}
    assert result.budget.remaining_steps == 3
    assert result.budget.remaining_model_calls == 6
    assert fake.route_calls() == 1
    assert fake.verify_calls() == 1


@pytest.mark.asyncio
async def test_routing_payload_is_plain_json() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    await build(fake, resolver=StubResolver()).run("Calculate 2 + 2", context={"locale": "ja-JP"})

    state = fake.requests[0]["state"]
    assert state["goal"] == "Calculate 2 + 2"
    assert state["step"] == 0
    assert state["context"] == {"locale": "ja-JP"}
    assert state["history"] == []
    assert state["last_result"] is None
    # The client pre-serializes with json.dumps(allow_nan=False); a mappingproxy
    # or tuple snapshot would surface as RequestValidationError instead.
    json.dumps(state, allow_nan=False)


@pytest.mark.asyncio
async def test_loop_continues_until_verifier_confirms_completion() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.3))
    fake.routes.append(route_answers("finish"))
    fake.verifies.append(verify_answers(0.9))

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "completed"
    assert result.state.step == 1
    assert len(result.traces) == 2
    assert result.traces[0].verification is not None
    assert result.traces[0].verification.completion_probability == 0.3
    assert result.traces[1].action == "finish"
    assert result.traces[1].executed is False
    assert result.traces[1].verification is not None
    assert result.traces[1].verification.completion_probability == 0.9
    assert fake.route_calls() == 2
    assert fake.verify_calls() == 2


@pytest.mark.asyncio
async def test_finish_before_any_step_skips_verification() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("finish"))

    result = await build(fake).run("Nothing to do")

    assert result.status == "completed"
    assert result.state.step == 0
    assert fake.route_calls() == 1
    assert fake.verify_calls() == 0
    assert result.traces[0].verification is None


@pytest.mark.asyncio
async def test_repeated_incomplete_verification_of_unchanged_state_fails() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.3))
    fake.routes.append(route_answers("finish"))
    fake.verifies.append(verify_answers(0.3))

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "failed"
    assert "no progress" in (result.diagnostic or "")
    assert fake.route_calls() == 2
    assert fake.verify_calls() == 2


@pytest.mark.asyncio
async def test_unregistered_action_fails_closed() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    registry = ShrinkingRegistry([CalculatorTool()])
    result = await build(fake, tools=registry, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "rejected"
    assert result.state.step == 0
    assert fake.route_calls() == 1
    assert fake.verify_calls() == 0


@pytest.mark.asyncio
async def test_write_risk_tool_requires_confirmation_despite_execute_outcome(
    tmp_path: Any,
) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("write_file", WRITE_FILE_CANDIDATES))

    registry = ToolRegistry([WriteFileTool(tmp_path)])
    result = await build(fake, tools=registry, resolver=StubResolver({"path": "a.txt", "content": "x"})).run(
        "Write a file"
    )

    assert result.status == "needs_confirmation"
    assert result.state.step == 0
    assert not (tmp_path / "a.txt").exists()


@pytest.mark.asyncio
async def test_external_risk_tool_requires_confirmation() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("send_mock_email", EMAIL_CANDIDATES))

    registry = ToolRegistry([MockEmailTool()])
    arguments = {"to": "a@example.com", "subject": "Hi", "body": "Hello"}
    result = await build(fake, tools=registry, resolver=StubResolver(arguments)).run("Send mail")

    assert result.status == "needs_confirmation"
    assert result.state.step == 0


@pytest.mark.asyncio
async def test_confirmation_binds_the_resolved_arguments(tmp_path: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("write_file", WRITE_FILE_CANDIDATES))
    fake.verifies.append(verify_answers(0.82))

    arguments = {"path": "note.txt", "content": "hello"}
    resolver = StubResolver(arguments)
    confirmation = StubConfirmation(approved=True)
    registry = ToolRegistry([WriteFileTool(tmp_path)])

    result = await build(
        fake, tools=registry, resolver=resolver, confirmation=confirmation
    ).run("Write a note", task_id="task-1")

    assert result.status == "completed"
    assert (tmp_path / "note.txt").read_text() == "hello"
    assert confirmation.calls == [("task-1", "write_file", arguments)]
    assert result.traces[0].confirmed is True
    assert dict(result.traces[0].arguments or {}) == arguments


@pytest.mark.asyncio
async def test_denied_confirmation_stops_the_run(tmp_path: Any) -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("write_file", WRITE_FILE_CANDIDATES))

    registry = ToolRegistry([WriteFileTool(tmp_path)])
    result = await build(
        fake,
        tools=registry,
        resolver=StubResolver({"path": "a.txt", "content": "x"}),
        confirmation=StubConfirmation(approved=False),
    ).run("Write a file")

    assert result.status == "needs_confirmation"
    assert result.traces[0].confirmed is False
    assert not (tmp_path / "a.txt").exists()


@pytest.mark.asyncio
async def test_route_requested_confirmation_is_honoured() -> None:
    fake = FakeJev()
    fake.routes.append(
        route_answers("calculator", requires_confirmation=0.9, risk=0.5)
    )

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "needs_confirmation"
    assert result.state.step == 0


@pytest.mark.asyncio
async def test_read_risk_tool_executes_without_a_handler() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "completed"
    assert result.traces[0].confirmed is None


@pytest.mark.asyncio
async def test_user_input_advances_state_and_continues() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("ask_user"))
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    user_input = StubUserInput("Tokyo")
    result = await build(fake, user_input=user_input, resolver=StubResolver()).run(
        "Find the weather"
    )

    assert result.status == "completed"
    assert user_input.calls == ["ask_user"]
    assert result.state.step == 2
    assert result.state.history[0].action == "ask_user"
    assert result.state.history[0].result == {"user_input": "Tokyo"}
    assert result.traces[0].executed is False
    assert result.traces[0].result == {"user_input": "Tokyo"}
    assert fake.verify_calls() == 1


@pytest.mark.asyncio
async def test_missing_user_input_stops_the_run() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("ask_user"))

    result = await build(fake, user_input=StubUserInput(None)).run("Find the weather")

    assert result.status == "needs_user_input"
    assert result.state.step == 0
    assert fake.verify_calls() == 0


@pytest.mark.asyncio
async def test_missing_user_input_handler_stops_the_run() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("ask_user"))

    result = await build(fake).run("Find the weather")

    assert result.status == "needs_user_input"


@pytest.mark.asyncio
async def test_delegation_advances_state_and_continues() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("delegate_to_llm"))
    fake.routes.append(route_answers("finish"))
    fake.verifies.append(verify_answers(0.9))

    delegate = StubDelegate()
    result = await build(fake, delegate=delegate).run("Reason about it")

    assert result.status == "completed"
    assert len(delegate.calls) == 1
    assert result.state.history[0].action == "delegate_to_llm"
    assert result.state.history[0].result == "The answer is 4."
    # Delegation is itself a model call, so it is charged against the budget.
    assert result.budget.remaining_model_calls == 8 - 1 - 1 - 1 - 1


@pytest.mark.asyncio
async def test_missing_delegate_handler_fails_closed() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("delegate_to_llm"))

    result = await build(fake).run("Reason about it")

    assert result.status == "failed"
    assert "no handler" in (result.diagnostic or "")
    assert result.state.step == 0


@pytest.mark.asyncio
async def test_delegate_returning_no_result_fails() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("delegate_to_llm"))

    result = await build(fake, delegate=StubDelegate(None)).run("Reason about it")

    assert result.status == "failed"
    assert result.state.step == 0


@pytest.mark.asyncio
async def test_step_budget_exhaustion_stops_the_run() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.3))

    result = await build(
        fake,
        budget=ExecutionBudget(max_steps=1, max_model_calls=2),
        resolver=StubResolver(),
    ).run("Calculate 2 + 2")

    assert result.status == "budget_exhausted"
    assert result.budget.remaining_steps == 0
    assert fake.route_calls() == 1
    assert fake.verify_calls() == 1


@pytest.mark.asyncio
async def test_exhausted_budget_before_any_decision_still_emits_a_trace() -> None:
    fake = FakeJev()

    result = await build(
        fake, budget=ExecutionBudget(max_steps=0, max_model_calls=0)
    ).run("Nothing to do")

    assert result.status == "budget_exhausted"
    assert fake.route_calls() == 0
    assert len(result.traces) == 1
    trace = result.traces[0]
    assert trace.step == 1
    assert trace.policy_outcome is None
    assert trace.route_confidence is None
    assert trace.executed is False


@pytest.mark.asyncio
async def test_model_call_budget_must_cover_route_and_verify() -> None:
    with pytest.raises(ValueError, match="max_model_calls"):
        Runner(
            client=JevClient(JevClientConfig(api_key="test-key")),
            model=TEST_MODEL,
            tools=ToolRegistry([CalculatorTool()]),
            budget=ExecutionBudget(max_steps=4, max_model_calls=4),
        )


@pytest.mark.asyncio
async def test_route_transport_failure_fails_the_run() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    runner = Runner(
        client=JevClient(JevClientConfig(api_key="test-key"), httpx.MockTransport(handler)),
        model=TEST_MODEL,
        tools=ToolRegistry([CalculatorTool()]),
        budget=ExecutionBudget(max_steps=2, max_model_calls=4),
    )

    result = await runner.run("Calculate 2 + 2")

    assert result.status == "failed"
    assert "route request failed" in (result.diagnostic or "")
    assert "transport" in (result.diagnostic or "")
    assert result.state.step == 0
    assert len(result.traces) == 1


@pytest.mark.asyncio
async def test_verification_transport_failure_fails_the_run() -> None:
    fake = FakeJev(fail_verify_transport=True)
    fake.routes.append(route_answers("calculator"))

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")

    assert result.status == "failed"
    assert "verification request failed" in (result.diagnostic or "")
    assert "transport" in (result.diagnostic or "")
    assert result.state.step == 1
    assert result.traces[0].executed is True
    assert fake.route_calls() == 1
    assert fake.verify_calls() == 1


@pytest.mark.asyncio
async def test_tool_input_rejection_fails_the_run() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    result = await build(fake, resolver=StubResolver({"expression": "import os"})).run(
        "Calculate 2 + 2"
    )

    assert result.status == "failed"
    assert "rejected its input" in (result.diagnostic or "")
    assert result.state.step == 0


@pytest.mark.asyncio
async def test_resolver_returning_a_non_mapping_fails_the_run() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))

    result = await build(fake, resolver=StubResolver(["2 + 2"])).run("Calculate 2 + 2")

    assert result.status == "failed"
    assert "argument mapping" in (result.diagnostic or "")
    assert result.state.step == 0


@pytest.mark.asyncio
async def test_unserializable_tool_output_fails_after_the_side_effect() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("opaque", OPAQUE_CANDIDATES))
    fake.verifies.append(verify_answers(0.82))

    result = await build(
        fake, tools=ToolRegistry([OpaqueTool()]), resolver=StubResolver({})
    ).run("Do something opaque")

    assert result.status == "failed"
    assert "state could not record" in (result.diagnostic or "")
    assert result.state.step == 0
    # The tool already ran, so the trace must show the execution.
    assert result.traces[0].executed is True
    assert fake.verify_calls() == 0


@pytest.mark.asyncio
async def test_traces_are_emitted_in_order_with_diagnostics() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.3))
    fake.routes.append(route_answers("finish"))
    fake.verifies.append(verify_answers(0.9))

    sink = RecordingSink()
    result = await build(fake, resolver=StubResolver(), trace_sink=sink).run(
        "Calculate 2 + 2", task_id="task-7"
    )

    assert [trace.step for trace in sink.traces] == [1, 2]
    assert [trace.task_id for trace in sink.traces] == ["task-7", "task-7"]
    assert list(result.traces) == sink.traces
    for trace in result.traces:
        assert trace.duration_ms >= 0
        assert trace.model == TEST_MODEL
        assert trace.state_snapshot is not None
        assert trace.route_confidence == 0.9
        assert trace.route_risk == 1.0
        assert trace.requires_confirmation == 0.1
        assert trace.needs_reasoning == 0.1


@pytest.mark.asyncio
async def test_broken_trace_sink_does_not_abort_the_run() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    result = await build(fake, resolver=StubResolver(), trace_sink=BrokenSink()).run(
        "Calculate 2 + 2"
    )

    assert result.status == "completed"
    assert len(result.traces) == 1


@pytest.mark.asyncio
async def test_completion_threshold_boundary_is_inclusive() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.75))

    result = await build(fake, resolver=StubResolver(), completion_threshold=0.75).run(
        "Calculate 2 + 2"
    )

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_completion_threshold_must_be_a_probability() -> None:
    fake = FakeJev()
    with pytest.raises(ValueError, match="completion_threshold"):
        build(fake, completion_threshold=1.5)


@pytest.mark.asyncio
async def test_model_identifier_is_required() -> None:
    fake = FakeJev()
    with pytest.raises(ValueError, match="model"):
        Runner(
            client=JevClient(JevClientConfig(api_key="test-key"), fake.transport()),
            model="  ",
            tools=ToolRegistry([CalculatorTool()]),
            budget=ExecutionBudget(max_steps=2, max_model_calls=4),
        )


@pytest.mark.asyncio
async def test_results_and_traces_are_immutable() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    result = await build(fake, resolver=StubResolver()).run("Calculate 2 + 2")
    trace = result.traces[0]

    with pytest.raises(FrozenInstanceError):
        result.status = "failed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        trace.executed = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        trace.arguments["expression"] = "9"  # type: ignore[index]


@pytest.mark.asyncio
async def test_caller_owned_context_is_not_mutated() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    context = {"locale": "ja-JP", "tags": ["a"]}
    await build(fake, resolver=StubResolver()).run("Calculate 2 + 2", context=context)

    assert context == {"locale": "ja-JP", "tags": ["a"]}


@pytest.mark.asyncio
async def test_task_identifier_is_generated_when_absent() -> None:
    fake = FakeJev()
    fake.routes.append(route_answers("finish"))

    result = await build(fake).run("Nothing to do")

    assert result.task_id
    assert result.traces[0].task_id == result.task_id


@pytest.mark.asyncio
async def test_transport_error_category_is_reported() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = JevClient(JevClientConfig(api_key="test-key"), httpx.MockTransport(handler))
    with pytest.raises(TransportError) as excinfo:
        await client.systemone(
            model=TEST_MODEL,
            state={"goal": "x"},
            questions={"q": NoulQuestion(instructions="Is this reachable?")},
        )

    assert excinfo.value.category == "transport"
