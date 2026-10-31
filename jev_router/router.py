from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union

from jev_router.clients.jev import (
    ChoiceAnswer,
    ChoiceQuestion,
    JevClient,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from jev_router.tools.registry import ToolRegistry

RiskDescription = Literal[
    "No meaningful side effects",
    "Minor reversible side effects",
    "Meaningful but reversible action",
    "External or consequential action",
    "Potentially destructive or irreversible action",
]
RiskAnswer = Union[float, RiskDescription]

RISK_LEVELS: tuple[RiskDescription, ...] = (
    "No meaningful side effects",
    "Minor reversible side effects",
    "Meaningful but reversible action",
    "External or consequential action",
    "Potentially destructive or irreversible action",
)

CONTROL_ACTIONS: dict[str, str] = {
    "ask_user": (
        "The goal is missing a detail only the user can supply, such as which "
        "file, which recipient, or what format"
    ),
    "delegate_to_llm": "The decision requires complex reasoning",
    "finish": "The task is already complete",
}


@dataclass(frozen=True)
class RouteDecision:
    action: str
    confidence: float
    risk: float
    risk_confidence: float
    requires_confirmation: float
    needs_reasoning: float
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class Router:
    def __init__(self, client: JevClient, model: str, tools: ToolRegistry) -> None:
        self._client = client
        self._model = model
        self._tools = tools

    async def route(self, state: Union[str, list[Any], dict[str, Any]]) -> RouteDecision:
        actions = {
            **{
                name: self._tools.get(name).description
                for name in self._tools.names()
            },
            **CONTROL_ACTIONS,
        }
        questions: dict[str, Question] = {
            "next_action": ChoiceQuestion(
                instructions="Choose the best next action to progress toward the user's goal.",
                criteria=actions,
            ),
            "risk": ScoreQuestion(
                instructions="Rate the risk of executing the selected next action.",
                criteria=list(RISK_LEVELS),
            ),
            "requires_confirmation": NoulQuestion(
                instructions="Should the user explicitly confirm before this action is executed?"
            ),
            "needs_reasoning": NoulQuestion(
                instructions="Does this action require complex reasoning by an LLM?"
            ),
        }
        response = await self._client.systemone(
            model=self._model,
            state=state,
            questions=questions,
        )
        action_answer = response.answers["next_action"]
        risk_answer = response.answers["risk"]
        confirmation_answer = response.answers["requires_confirmation"]
        reasoning_answer = response.answers["needs_reasoning"]
        if not isinstance(action_answer, ChoiceAnswer):
            raise TypeError("next_action 必须是 choice 类型的回答")
        if not isinstance(risk_answer, ScoreAnswer):
            raise TypeError("risk 必须是 score 类型的回答")
        if not isinstance(confirmation_answer, NoulAnswer):
            raise TypeError("requires_confirmation 必须是 noul 类型的回答")
        if not isinstance(reasoning_answer, NoulAnswer):
            raise TypeError("needs_reasoning 必须是 noul 类型的回答")
        return RouteDecision(
            action=action_answer.choice,
            confidence=action_answer.confidence,
            risk=risk_answer.score,
            risk_confidence=risk_answer.confidence,
            requires_confirmation=confirmation_answer.noul,
            needs_reasoning=reasoning_answer.noul,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
