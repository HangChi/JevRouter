from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# API-level statuses for a run that has not reached a terminal RunStatus yet.
RUNNING = "running"
AWAITING_CONFIRMATION = "awaiting_confirmation"
AWAITING_INPUT = "awaiting_input"


class SubmitTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] | None = None

    @field_validator("goal")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal must not be blank")
        return value


class SubmitTaskResponse(BaseModel):
    task_id: str
    status: str


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class ProvideInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)


class PendingConfirmationView(BaseModel):
    action: str
    arguments: dict[str, Any]
    step: int


class PendingInputView(BaseModel):
    question: str
    step: int


class TaskView(BaseModel):
    task_id: str
    goal: str
    status: str
    step: int
    diagnostic: str | None = None
    pending_confirmation: PendingConfirmationView | None = None
    pending_input: PendingInputView | None = None


class TaskSummary(BaseModel):
    task_id: str
    goal: str
    status: str
    step: int


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]


class TraceView(BaseModel):
    step: int
    action: str
    policy_outcome: str | None = None
    policy_reason: str | None = None
    executed: bool = False
    result: Any | None = None
    route_confidence: float | None = None
    route_risk: float | None = None
    requires_confirmation: float | None = None
    needs_reasoning: float | None = None
    confirmed: bool | None = None
    arguments: dict[str, Any] | None = None
    completion_probability: float | None = None
    quality_score: float | None = None
    state_snapshot: dict[str, Any] | None = None
    duration_ms: int = 0

    @classmethod
    def from_trace(cls, trace: Any) -> TraceView:
        verification = trace.verification
        return cls(
            step=trace.step,
            action=trace.action,
            policy_outcome=trace.policy_outcome,
            policy_reason=trace.policy_reason,
            executed=trace.executed,
            result=trace.result,
            route_confidence=trace.route_confidence,
            route_risk=trace.route_risk,
            requires_confirmation=trace.requires_confirmation,
            needs_reasoning=trace.needs_reasoning,
            confirmed=trace.confirmed,
            arguments=None if trace.arguments is None else dict(trace.arguments),
            completion_probability=(
                None if verification is None else verification.completion_probability
            ),
            quality_score=None if verification is None else verification.quality_score,
            state_snapshot=None if trace.state_snapshot is None else dict(trace.state_snapshot),
            duration_ms=trace.duration_ms,
        )


class TraceListResponse(BaseModel):
    task_id: str
    traces: list[TraceView]
