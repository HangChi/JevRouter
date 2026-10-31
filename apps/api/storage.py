from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.api.schemas import (
    ComparisonMetricsPayload,
    EvalCaseOutcomePayload,
    EvalRunView,
    RecordEvalRunRequest,
)
from jev_router.runner import RunResult, StepTrace
from jev_router.serialization import jsonable
from jev_router.verifier import VerificationDecision

SCHEMA_VERSION = 2
PAYLOAD_VERSION = 1

# 用于 trace 仍在写入中的任务的存储状态；一旦调用 record()，它会被
# 终态的 RunStatus 取代。
RUNNING_STATUS = "running"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    step INTEGER NOT NULL,
    diagnostic TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    final_state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_steps (
    task_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    action TEXT NOT NULL,
    policy_outcome TEXT,
    policy_reason TEXT,
    route_confidence REAL,
    route_risk REAL,
    requires_confirmation REAL,
    needs_reasoning REAL,
    confirmed INTEGER,
    executed INTEGER NOT NULL,
    result TEXT,
    arguments TEXT,
    state_snapshot TEXT NOT NULL,
    model TEXT,
    duration_ms INTEGER NOT NULL,
    PRIMARY KEY (task_id, step),
    FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evaluations (
    task_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    completion_probability REAL NOT NULL,
    quality_score REAL NOT NULL,
    quality_confidence REAL NOT NULL,
    quality_legend TEXT NOT NULL,
    model TEXT NOT NULL,
    PRIMARY KEY (task_id, step),
    FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS agent_steps_task ON agent_steps (task_id, step);
CREATE INDEX IF NOT EXISTS evaluations_task ON evaluations (task_id, step);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metrics TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_case_results (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, case_id, mode),
    FOREIGN KEY (run_id) REFERENCES eval_runs (run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS eval_case_results_run ON eval_case_results (run_id);
"""


class StorageError(Exception):
    """当存储的载荷无法编码、解码或被理解时抛出。"""


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    goal: str
    status: str
    step: int
    diagnostic: str | None
    created_at: str
    updated_at: str
    final_state: dict[str, Any]


@dataclass(frozen=True)
class EvalRunRecord:
    """一次已存储的评测运行，不含明细行，供列表视图使用。"""

    run_id: str
    mode: str
    created_at: str
    case_count: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _degrade(value: Any) -> Any:
    """尽最大努力做转换，只标记 JSON 无法承载的值。"""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"__unserializable__": "non-finite float"}
    if isinstance(value, Mapping):
        return {str(key): _degrade(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_degrade(item) for item in value]
    return {"__unserializable__": type(value).__name__}


def _encode(value: Any) -> str:
    """把一个值序列化成带版本号的 JSON 信封。

    状态快照已经拒绝的值仍可能进入 trace，因为工具是先运行、后接受输出的。
    把出问题的叶子节点降级，能让运行的其余部分保持可读，而不是整段丢失。
    """
    try:
        data = jsonable(value)
        text = json.dumps(data, allow_nan=False, sort_keys=True)
    except (ValueError, TypeError):
        text = json.dumps(_degrade(value), sort_keys=True)
    return json.dumps({"version": PAYLOAD_VERSION, "data": json.loads(text)}, sort_keys=True)


def _decode(raw: str, field: str) -> Any:
    try:
        envelope = json.loads(raw)
        version = envelope["version"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise StorageError(f"存储的 {field} 不是带版本的载荷") from exc
    if version != PAYLOAD_VERSION:
        raise StorageError(
            f"存储的 {field} 使用 payload 版本 {version}，"
            f"但本构建读取的是版本 {PAYLOAD_VERSION}"
        )
    return envelope["data"]


def _verification_to_row(task_id: str, step: int, decision: VerificationDecision) -> tuple[Any, ...]:
    return (
        task_id,
        step,
        decision.completion_probability,
        decision.quality_score,
        decision.quality_confidence,
        json.dumps(list(decision.quality_legend)),
        decision.model,
    )


class IncrementalSink:
    """一个 ``TraceSink``，在 Runner 每产出一个步骤时就写入该步骤。

    它必须暴露 ``emit`` 方法而不能只是一个裸可调用对象：Runner 的
    ``TraceSink`` 是用该方法定义的 Protocol，缺失属性会被 Runner 自身的
    sink 错误保护逻辑吞掉。
    """

    def __init__(self, store: TraceStore) -> None:
        self._store = store

    def emit(self, trace: StepTrace) -> None:
        with self._store._connection:
            self._store._ensure_task(trace)
            self._store._write_step(trace)


class TraceStore:
    """运行 trace 的 SQLite 持久化。

    核心包刻意不包含任何数据库代码，因此这部分放在 API 层，并且只消费
    Runner 已经产出的不可变记录。写入是同步且短暂的；该存储不是线程安全的，
    应当由单个事件循环驱动。
    """

    def __init__(
        self,
        path: str | Path,
        *,
        redact: Callable[[Any], Any] | None = None,
    ) -> None:
        self._path = Path(path)
        if self._path.parent and not self._path.parent.exists():
            raise StorageError(f"数据库目录不存在：{self._path.parent}")
        self._redact = redact
        # 连接在构造该存储的位置创建，而那未必是事件循环运行的线程。
        # 所有访问仍然通过那一个循环串行化，因此放开线程检查是安全的。
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._apply_schema()

    def _apply_schema(self) -> None:
        current = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise StorageError(
                f"数据库 schema 版本 {current} 比支持的版本 {SCHEMA_VERSION} 更新"
            )
        with self._connection:
            self._connection.executescript(_SCHEMA)
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> TraceStore:  # noqa: PYI034 - typing.Self needs Python 3.11
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def record(self, result: RunResult) -> None:
        """持久化一次已完成的运行。对同一任务重复调用是安全的。"""
        state = result.state
        final_state = {
            "goal": state.goal,
            "step": state.step,
            "context": jsonable(state.context),
            "history": [
                {"step": record.step, "action": record.action, "result": jsonable(record.result)}
                for record in state.history
            ],
            "last_result": jsonable(state.last_result),
        }
        now = _now()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO tasks (task_id, goal, status, step, diagnostic,
                                   created_at, updated_at, final_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (task_id) DO UPDATE SET
                    goal = excluded.goal,
                    status = excluded.status,
                    step = excluded.step,
                    diagnostic = excluded.diagnostic,
                    updated_at = excluded.updated_at,
                    final_state = excluded.final_state
                """,
                (
                    result.task_id,
                    state.goal,
                    result.status,
                    state.step,
                    result.diagnostic,
                    now,
                    now,
                    _encode(final_state),
                ),
            )
            for trace in result.traces:
                self._write_step(trace)

    def sink(self) -> IncrementalSink:
        """返回一个 TraceSink，在 Runner 每产出一个步骤时就写入该步骤。"""
        return IncrementalSink(self)

    def _ensure_task(self, trace: StepTrace) -> None:
        self._connection.execute(
            """
            INSERT INTO tasks (task_id, goal, status, step, diagnostic,
                               created_at, updated_at, final_state)
            VALUES (?, ?, ?, 0, NULL, ?, ?, ?)
            ON CONFLICT (task_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (
                trace.task_id,
                trace.state_snapshot.get("goal", "") if trace.state_snapshot else "",
                RUNNING_STATUS,
                _now(),
                _now(),
                _encode({}),
            ),
        )

    def _write_step(self, trace: StepTrace) -> None:
        task_id = trace.task_id
        self._connection.execute(
            """
            INSERT INTO agent_steps (task_id, step, action, policy_outcome, policy_reason,
                                     route_confidence, route_risk, requires_confirmation,
                                     needs_reasoning, confirmed, executed, result, arguments,
                                     state_snapshot, model, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (task_id, step) DO UPDATE SET
                action = excluded.action,
                policy_outcome = excluded.policy_outcome,
                policy_reason = excluded.policy_reason,
                route_confidence = excluded.route_confidence,
                route_risk = excluded.route_risk,
                requires_confirmation = excluded.requires_confirmation,
                needs_reasoning = excluded.needs_reasoning,
                confirmed = excluded.confirmed,
                executed = excluded.executed,
                result = excluded.result,
                arguments = excluded.arguments,
                state_snapshot = excluded.state_snapshot,
                model = excluded.model,
                duration_ms = excluded.duration_ms
            """,
            (
                task_id,
                trace.step,
                trace.action,
                trace.policy_outcome,
                trace.policy_reason,
                trace.route_confidence,
                trace.route_risk,
                trace.requires_confirmation,
                trace.needs_reasoning,
                None if trace.confirmed is None else int(trace.confirmed),
                int(trace.executed),
                None if trace.result is None else _encode(self._scrub(trace.result)),
                None if trace.arguments is None else _encode(self._scrub(trace.arguments)),
                _encode(self._scrub(trace.state_snapshot)),
                trace.model,
                trace.duration_ms,
            ),
        )
        self._connection.execute("DELETE FROM evaluations WHERE task_id = ? AND step = ?", (task_id, trace.step))
        if trace.verification is not None:
            self._connection.execute(
                """
                INSERT INTO evaluations (task_id, step, completion_probability, quality_score,
                                         quality_confidence, quality_legend, model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                _verification_to_row(task_id, trace.step, trace.verification),
            )

    def _scrub(self, value: Any) -> Any:
        return value if self._redact is None else self._redact(value)

    def load_task(self, task_id: str) -> TaskRecord | None:
        row = self._connection.execute(
            """
            SELECT task_id, goal, status, step, diagnostic, created_at, updated_at, final_state
            FROM tasks WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return TaskRecord(
            task_id=row[0],
            goal=row[1],
            status=row[2],
            step=row[3],
            diagnostic=row[4],
            created_at=row[5],
            updated_at=row[6],
            final_state=_decode(row[7], "final_state"),
        )

    def list_tasks(self, *, limit: int = 50) -> tuple[TaskRecord, ...]:
        if limit < 1:
            raise ValueError("limit 必须为正数")
        rows = self._connection.execute(
            """
            SELECT task_id, goal, status, step, diagnostic, created_at, updated_at, final_state
            FROM tasks ORDER BY created_at DESC, task_id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(
            TaskRecord(
                task_id=row[0],
                goal=row[1],
                status=row[2],
                step=row[3],
                diagnostic=row[4],
                created_at=row[5],
                updated_at=row[6],
                final_state=_decode(row[7], "final_state"),
            )
            for row in rows
        )

    def load_traces(self, task_id: str) -> tuple[StepTrace, ...]:
        """为某个任务重建 Runner 的 trace，最新步骤排在最后。"""
        rows = self._connection.execute(
            """
            SELECT s.step, s.action, s.policy_outcome, s.policy_reason, s.route_confidence,
                   s.route_risk, s.requires_confirmation, s.needs_reasoning, s.confirmed,
                   s.executed, s.result, s.arguments, s.state_snapshot, s.model, s.duration_ms,
                   e.completion_probability, e.quality_score, e.quality_confidence,
                   e.quality_legend, e.model
            FROM agent_steps s
            LEFT JOIN evaluations e ON e.task_id = s.task_id AND e.step = s.step
            WHERE s.task_id = ?
            ORDER BY s.step
            """,
            (task_id,),
        ).fetchall()
        traces: list[StepTrace] = []
        for row in rows:
            verification = None
            if row[15] is not None:
                verification = VerificationDecision(
                    completion_probability=row[15],
                    quality_score=row[16],
                    quality_confidence=row[17],
                    quality_legend=tuple(json.loads(row[18])),
                    model=row[19],
                )
            traces.append(
                StepTrace(
                    step=row[0],
                    task_id=task_id,
                    action=row[1],
                    policy_outcome=row[2],
                    policy_reason=row[3],
                    route_confidence=row[4],
                    route_risk=row[5],
                    requires_confirmation=row[6],
                    needs_reasoning=row[7],
                    confirmed=None if row[8] is None else bool(row[8]),
                    executed=bool(row[9]),
                    result=None if row[10] is None else _decode(row[10], "result"),
                    arguments=None if row[11] is None else _decode(row[11], "arguments"),
                    state_snapshot=_decode(row[12], "state_snapshot"),
                    model=row[13],
                    duration_ms=row[14],
                    verification=verification,
                )
            )
        return tuple(traces)

    def record_eval_run(self, request: RecordEvalRunRequest) -> None:
        """持久化一次已完成的评测运行。对同一 run id 重复调用是安全的。

        指标存放在运行行上，每个用例结果各占一行，因此一次 compare 运行的
        100 行仍然可查询，而不必解包一整块数据。重复记录会替换该运行的行，
        而不是在其上追加。
        """
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO eval_runs (run_id, mode, created_at, metrics)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (run_id) DO UPDATE SET
                    mode = excluded.mode,
                    created_at = excluded.created_at,
                    metrics = excluded.metrics
                """,
                (
                    request.run_id,
                    request.mode,
                    request.created_at,
                    _encode(request.metrics.model_dump(mode="json")),
                ),
            )
            self._connection.execute(
                "DELETE FROM eval_case_results WHERE run_id = ?", (request.run_id,)
            )
            for outcome in request.outcomes:
                self._connection.execute(
                    """
                    INSERT INTO eval_case_results (run_id, case_id, mode, payload)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        request.run_id,
                        outcome.case_id,
                        outcome.mode,
                        _encode(outcome.model_dump(mode="json")),
                    ),
                )

    def list_eval_runs(self, *, limit: int = 50) -> tuple[EvalRunRecord, ...]:
        if limit < 1:
            raise ValueError("limit 必须为正数")
        rows = self._connection.execute(
            """
            SELECT r.run_id, r.mode, r.created_at,
                   (SELECT COUNT(DISTINCT case_id) FROM eval_case_results c
                    WHERE c.run_id = r.run_id)
            FROM eval_runs r
            ORDER BY r.created_at DESC, r.run_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(
            EvalRunRecord(
                run_id=row[0], mode=row[1], created_at=row[2], case_count=row[3]
            )
            for row in rows
        )

    def load_eval_run(self, run_id: str) -> EvalRunView | None:
        """重建一次已存储的运行，不做额外排序：行按用例顺序返回。

        排序键是 `(case_id, mode)`，这样一个用例在两侧路由层的行彼此相邻，
        同一用例集的两个运行也能逐行对齐。
        """
        row = self._connection.execute(
            "SELECT run_id, mode, created_at, metrics FROM eval_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        outcome_rows = self._connection.execute(
            """
            SELECT payload FROM eval_case_results
            WHERE run_id = ? ORDER BY case_id, mode
            """,
            (run_id,),
        ).fetchall()
        outcomes = [
            EvalCaseOutcomePayload.model_validate(_decode(item[0], "eval case outcome"))
            for item in outcome_rows
        ]
        return EvalRunView(
            run_id=row[0],
            mode=row[1],
            created_at=row[2],
            case_count=len({outcome.case_id for outcome in outcomes}),
            metrics=ComparisonMetricsPayload.model_validate(
                _decode(row[3], "eval metrics")
            ),
            outcomes=outcomes,
        )

