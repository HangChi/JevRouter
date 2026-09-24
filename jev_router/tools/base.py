from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

RiskLevel = Literal["read", "write", "external"]


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    output: dict[str, Any]


class Tool(Protocol):
    name: str
    description: str
    risk: RiskLevel
    # The model `execute` validates its input against. A caller that has to
    # synthesize arguments (an LLM resolver) reads the schema from here rather
    # than from a second description that could drift from the real check.
    input_model: type[BaseModel]

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
