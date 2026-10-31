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
    # `execute` 用于校验输入的模型。需要自行构造参数（例如 LLM 解析器）的
    # 调用方从这里读取 schema，而不是依赖另一份可能与真实校验漂移的描述。
    input_model: type[BaseModel]

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
