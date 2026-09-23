from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jev_router.clients.jev import (
    JevClient,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from jev_router.serialization import jsonable
from jev_router.state import TaskState

QUALITY_LEVELS: tuple[str, ...] = (
    "Not useful",
    "Partially useful",
    "Mostly sufficient",
    "Fully sufficient",
)

_COMPLETION_QUESTION = "task_complete"
_QUALITY_QUESTION = "result_quality"


@dataclass(frozen=True)
class VerificationDecision:
    completion_probability: float
    quality_score: float
    quality_confidence: float
    quality_legend: tuple[str, ...]
    model: str


class Verifier:
    def __init__(self, client: JevClient, model: str) -> None:
        self._client = client
        self._model = model

    async def verify(self, state: TaskState) -> VerificationDecision:
        if state.step < 1 or not state.history:
            raise ValueError("verification requires at least one completed step")
        if state.last_result is None:
            raise ValueError("verification requires a latest result")
        questions: dict[str, Question] = {
            _COMPLETION_QUESTION: NoulQuestion(
                instructions="Does the current result satisfy the user goal?"
            ),
            _QUALITY_QUESTION: ScoreQuestion(
                instructions="Rate how well the result satisfies the goal.",
                criteria=list(QUALITY_LEVELS),
            ),
        }
        response = await self._client.systemone(
            model=self._model,
            state=self._build_state(state),
            questions=questions,
        )
        completion_answer = response.answers[_COMPLETION_QUESTION]
        quality_answer = response.answers[_QUALITY_QUESTION]
        if not isinstance(completion_answer, NoulAnswer):
            raise TypeError("task_complete must be a noul answer")
        if not isinstance(quality_answer, ScoreAnswer):
            raise TypeError("result_quality must be a score answer")
        return VerificationDecision(
            completion_probability=completion_answer.noul,
            quality_score=quality_answer.score,
            quality_confidence=quality_answer.confidence,
            quality_legend=tuple(quality_answer.legend),
            model=response.model,
        )

    @staticmethod
    def _build_state(state: TaskState) -> dict[str, Any]:
        latest = state.history[-1]
        return {
            "goal": state.goal,
            "step": state.step,
            "action": latest.action,
            "result": jsonable(state.last_result),
            "context": jsonable(state.context),
            "history": [
                {
                    "step": record.step,
                    "action": record.action,
                    "result": jsonable(record.result),
                }
                for record in state.history
            ],
        }
