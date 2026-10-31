from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from support import (
    TEST_MODEL,
    FakeJev,
    StubResolver,
    eval_run,
    route_answers,
    verify_answers,
)

from apps.api.storage import (
    PAYLOAD_VERSION,
    RUNNING_STATUS,
    SCHEMA_VERSION,
    StorageError,
    TraceStore,
)
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.runner import Runner, StepTrace
from jev_router.state import ExecutionBudget, TaskState
from jev_router.tools import CalculatorTool, ToolRegistry
from jev_router.verifier import QUALITY_LEVELS, VerificationDecision


def verification(step: int = 1) -> VerificationDecision:
    return VerificationDecision(
        completion_probability=0.82,
        quality_score=3.0,
        quality_confidence=0.6,
        quality_legend=QUALITY_LEVELS,
        model=TEST_MODEL,
    )


def trace(
    step: int,
    *,
    task_id: str = "task-1",
    action: str = "calculator",
    result: Any = None,
    with_verification: bool = True,
) -> StepTrace:
    return StepTrace(
        step=step,
        task_id=task_id,
        action=action,
        executed=result is not None,
        result=result,
        policy_outcome="execute",
        policy_reason="The registered action is permitted by the configured thresholds.",
        route_confidence=0.9,
        route_risk=1.0,
        requires_confirmation=0.1,
        needs_reasoning=0.1,
        arguments={"expression": "2 + 2"} if result is not None else None,
        verification=verification(step) if with_verification else None,
        state_snapshot={"goal": "Calculate 2 + 2", "step": step - 1, "history": []},
        model=TEST_MODEL,
        duration_ms=7,
    )


def make_result(
    task_id: str = "task-1",
    *,
    status: str = "completed",
    traces: tuple[StepTrace, ...] = (),
    goal: str = "Calculate 2 + 2",
    diagnostic: str | None = None,
):
    from jev_router.runner import RunResult

    state = TaskState(goal=goal)
    for item in traces:
        try:
            state = state.advance(item.action, item.result)
        except ValueError:
            # 当结果无法生成快照时，执行循环只记录该步骤，而不会推进状态，
            # 这里正是这种情况。
            pass
    return RunResult(
        status=status,  # type: ignore[arg-type]
        task_id=task_id,
        state=state,
        budget=ExecutionBudget(max_steps=4, max_model_calls=8),
        traces=traces,
        diagnostic=diagnostic,
    )


@pytest.fixture
def store_factory(tmp_path: Path):
    created: list[TraceStore] = []

    def make(**kwargs: Any) -> TraceStore:
        instance = TraceStore(tmp_path / f"traces-{len(created)}.db", **kwargs)
        created.append(instance)
        return instance

    yield make
    for instance in created:
        instance.close()


@pytest.fixture
def store(store_factory: Any) -> TraceStore:
    return store_factory()


def test_round_trip_preserves_every_trace_field(store: TraceStore) -> None:
    traces = (trace(1, result={"result": 4.0}), trace(2, action="finish", result=None, with_verification=False))
    store.record(make_result(traces=traces))

    loaded = store.load_traces("task-1")

    assert loaded == traces


def test_task_record_carries_the_terminal_status(store: TraceStore) -> None:
    store.record(
        make_result(
            status="needs_confirmation",
            traces=(trace(1, result={"result": 4.0}),),
            diagnostic="explicit confirmation was not granted",
        )
    )

    record = store.load_task("task-1")

    assert record is not None
    assert record.task_id == "task-1"
    assert record.goal == "Calculate 2 + 2"
    assert record.status == "needs_confirmation"
    assert record.step == 1
    assert record.diagnostic == "explicit confirmation was not granted"
    assert record.final_state["last_result"] == {"result": 4.0}
    assert record.final_state["history"][0]["action"] == "calculator"
    assert record.created_at == record.updated_at


def test_evaluations_are_stored_separately_from_steps(store: TraceStore) -> None:
    store.record(make_result(traces=(trace(1, result={"result": 4.0}),)))

    row = store._connection.execute(
        "SELECT completion_probability, quality_score, model FROM evaluations WHERE task_id = ?",
        ("task-1",),
    ).fetchone()

    assert row == (0.82, 3.0, "test-model")


def test_incremental_sink_writes_before_the_run_finishes(store: TraceStore) -> None:
    store.sink().emit(trace(1, result={"result": 4.0}))

    record = store.load_task("task-1")
    assert record is not None
    assert record.status == RUNNING_STATUS
    assert record.step == 0
    assert len(store.load_traces("task-1")) == 1


def test_record_finalizes_a_run_written_by_the_sink(store: TraceStore) -> None:
    emit = store.sink()
    emit.emit(trace(1, result={"result": 4.0}))
    store.record(make_result(status="completed", traces=(trace(1, result={"result": 4.0}),)))

    record = store.load_task("task-1")
    assert record is not None
    assert record.status == "completed"
    assert record.step == 1
    assert len(store.load_traces("task-1")) == 1


def test_stored_payloads_carry_their_version(store: TraceStore) -> None:
    store.record(make_result(traces=(trace(1, result={"result": 4.0}),)))

    raw = store._connection.execute(
        "SELECT result, state_snapshot FROM agent_steps WHERE task_id = ?", ("task-1",)
    ).fetchone()

    for column in raw:
        envelope = json.loads(column)
        assert envelope["version"] == PAYLOAD_VERSION


def test_schema_version_is_recorded(store: TraceStore) -> None:
    version = store._connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()

    with pytest.raises(StorageError, match="比支持的版本"):
        TraceStore(path)


def test_an_unknown_payload_version_is_refused(store: TraceStore) -> None:
    store.record(make_result(traces=(trace(1, result={"result": 4.0}),)))
    store._connection.execute(
        "UPDATE agent_steps SET state_snapshot = ? WHERE task_id = ?",
        (json.dumps({"version": 99, "data": {}}), "task-1"),
    )
    store._connection.commit()

    with pytest.raises(StorageError, match="payload 版本 99"):
        store.load_traces("task-1")


def test_a_malformed_payload_is_refused(store: TraceStore) -> None:
    store.record(make_result(traces=(trace(1, result={"result": 4.0}),)))
    store._connection.execute(
        "UPDATE agent_steps SET state_snapshot = ? WHERE task_id = ?",
        ("not json at all", "task-1"),
    )
    store._connection.commit()

    with pytest.raises(StorageError, match="不是带版本的载荷"):
        store.load_traces("task-1")


def test_redaction_reaches_result_arguments_and_snapshot(store_factory: Any) -> None:
    store = store_factory(redact=lambda value: {"redacted": True} if isinstance(value, Mapping) else value)
    store.record(make_result(traces=(trace(1, result={"result": 4.0}),)))

    row = store._connection.execute(
        "SELECT result, arguments, state_snapshot FROM agent_steps WHERE task_id = ?", ("task-1",)
    ).fetchone()

    assert all(json.loads(column)["data"] == {"redacted": True} for column in row)


def test_unserializable_results_degrade_instead_of_failing(store: TraceStore) -> None:
    store.record(make_result(traces=(trace(1, result={"value": object()}),)))

    loaded = store.load_traces("task-1")

    # 只有出问题的叶子节点会被替换，因此可读的部分得以保留。
    assert loaded[0].result == {"value": {"__unserializable__": "object"}}


def test_an_unserializable_result_still_records_the_task(store: TraceStore) -> None:
    store.record(make_result(traces=(trace(1, result={"value": object()}),)))

    record = store.load_task("task-1")
    assert record is not None
    assert record.status == "completed"


def test_list_tasks_orders_by_creation(tmp_path: Path) -> None:
    with TraceStore(tmp_path / "traces.db") as store:
        store.record(make_result("task-a", goal="First"))
        store.record(make_result("task-b", goal="Second"))
        listed = store.list_tasks()

        assert [record.task_id for record in listed] == ["task-b", "task-a"]
        assert store.list_tasks(limit=1)[0].task_id == "task-b"
        with pytest.raises(ValueError, match="limit 必须为正数"):
            store.list_tasks(limit=0)


def test_unknown_tasks_read_as_empty(store: TraceStore) -> None:
    assert store.load_task("missing") is None
    assert store.load_traces("missing") == ()


def test_recording_twice_is_idempotent(store: TraceStore) -> None:
    traces = (trace(1, result={"result": 4.0}),)
    store.record(make_result(traces=traces))
    store.record(make_result(traces=traces))

    assert len(store.load_traces("task-1")) == 1
    assert len(store.list_tasks()) == 1


def test_separate_tasks_do_not_collide(store: TraceStore) -> None:
    store.record(make_result("task-a", traces=(trace(1, task_id="task-a", result={"result": 4.0}),)))
    store.record(make_result("task-b", traces=(trace(1, task_id="task-b", result={"result": 9.0}),)))

    assert store.load_traces("task-a")[0].result == {"result": 4.0}
    assert store.load_traces("task-b")[0].result == {"result": 9.0}


def test_a_missing_database_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="目录不存在"):
        TraceStore(tmp_path / "absent" / "traces.db")


def test_the_store_can_be_used_as_a_context_manager(store_factory: Any) -> None:
    store = store_factory()
    with store as entered:
        assert entered is store
        entered.record(make_result(traces=(trace(1, result={"result": 4.0}),)))

    with pytest.raises(sqlite3.ProgrammingError):
        store._connection.execute("SELECT 1")


@pytest.mark.asyncio
async def test_no_credential_reaches_the_database(tmp_path: Path) -> None:
    secret = "sk-live-should-never-be-stored"
    fake = FakeJev()
    fake.routes.append(route_answers("calculator"))
    fake.verifies.append(verify_answers(0.82))

    database = tmp_path / "traces.db"
    with TraceStore(database) as store:
        runner = Runner(
            client=JevClient(JevClientConfig(api_key=secret), fake.transport()),
            model=TEST_MODEL,
            tools=ToolRegistry([CalculatorTool()]),
            budget=ExecutionBudget(max_steps=4, max_model_calls=8),
            resolver=StubResolver(),
            trace_sink=store.sink(),
        )
        result = await runner.run("Calculate 2 + 2")
        # 此时 sink 必须已经写入该步骤；record() 只负责收尾。
        assert len(store.load_traces(result.task_id)) == 1
        assert store.load_task(result.task_id) is not None
        assert store.load_task(result.task_id).status == RUNNING_STATUS
        store.record(result)
        assert store.load_task(result.task_id).status == "completed"

    assert result.status == "completed"
    assert fake.route_calls() == 1
    assert fake.verify_calls() == 1
    assert secret.encode() not in database.read_bytes()


def test_an_eval_run_round_trips(store: TraceStore) -> None:
    store.record_eval_run(eval_run())

    view = store.load_eval_run("run-1")

    assert view is not None
    assert view.run_id == "run-1"
    assert view.mode == "compare"
    assert view.case_count == 2
    assert view.metrics.agreement_rate == 0.0
    assert view.metrics.jev is not None
    assert view.metrics.jev.expected_match_rate == 1.0
    assert view.metrics.llm is not None
    assert view.metrics.llm.escalation_count is None
    assert [(o.case_id, o.mode) for o in view.outcomes] == [
        ("case-1", "jev"),
        ("case-1", "llm"),
        ("case-2", "jev"),
        ("case-2", "llm"),
    ]
    assert view.outcomes[1].action == "web_search"
    assert view.outcomes[1].input_tokens == 10


def test_recording_the_same_eval_run_replaces_its_rows(store: TraceStore) -> None:
    store.record_eval_run(eval_run())
    store.record_eval_run(eval_run(case_ids=("case-9",)))

    view = store.load_eval_run("run-1")

    assert view is not None
    assert view.case_count == 1
    assert [o.case_id for o in view.outcomes] == ["case-9", "case-9"]


def test_eval_runs_are_listed_newest_first(store: TraceStore) -> None:
    store.record_eval_run(
        eval_run("run-old", case_ids=("case-1",), created_at="2026-09-23T00:00:00+00:00")
    )
    store.record_eval_run(
        eval_run(
            "run-new",
            case_ids=("case-1", "case-2", "case-3"),
            created_at="2026-09-24T00:00:00+00:00",
        )
    )

    listed = store.list_eval_runs()

    assert [record.run_id for record in listed] == ["run-new", "run-old"]
    assert [record.case_count for record in listed] == [3, 1]
    assert listed[0].mode == "compare"


def test_listing_eval_runs_respects_the_limit(store: TraceStore) -> None:
    for index in range(3):
        store.record_eval_run(eval_run(f"run-{index}", case_ids=("case-1",)))

    assert len(store.list_eval_runs(limit=2)) == 2
    with pytest.raises(ValueError, match="limit 必须为正数"):
        store.list_eval_runs(limit=0)


def test_an_unknown_eval_run_reads_as_missing(store: TraceStore) -> None:
    assert store.load_eval_run("nope") is None
    assert store.list_eval_runs() == ()


def test_a_tampered_eval_payload_is_refused(store: TraceStore) -> None:
    store.record_eval_run(eval_run())
    store._connection.execute(
        "UPDATE eval_runs SET metrics = ? WHERE run_id = ?",
        (json.dumps({"version": 99, "data": {}}), "run-1"),
    )
    store._connection.commit()

    with pytest.raises(StorageError, match="payload 版本 99"):
        store.load_eval_run("run-1")


def test_a_version_one_database_still_opens_and_gains_the_tables(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE tasks (task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL,
                            step INTEGER NOT NULL, diagnostic TEXT, created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL, final_state TEXT NOT NULL);
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    connection.close()

    with TraceStore(path) as store:
        store.record_eval_run(eval_run())
        assert store.load_eval_run("run-1") is not None
