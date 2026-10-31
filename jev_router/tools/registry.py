from __future__ import annotations

from collections.abc import Iterable

from jev_router.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if not tool.name or tool.name.strip() != tool.name:
            raise ValueError("工具名称不得为空且不得含首尾空白")
        if tool.name in self._tools:
            raise ValueError("工具已注册")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError("工具未注册") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def execute(self, name: str, input: dict[str, object]) -> object:
        return self.get(name).execute(input)
