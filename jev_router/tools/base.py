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

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
