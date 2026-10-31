from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from jev_router.tools.base import RiskLevel, ToolResult
from jev_router.tools.knowledge_search import SearchDocument, SearchInput


class WebSearchMockTool:
    name = "web_search"
    description = "Search deterministic, injected mock web results; performs no network requests."
    risk: RiskLevel = "read"
    input_model: type[BaseModel] = SearchInput

    def __init__(self, results: Sequence[SearchDocument | dict[str, Any]] = ()) -> None:
        self._results = tuple(SearchDocument.model_validate(result) for result in results)

    def execute(self, input: dict[str, Any]) -> ToolResult:
        try:
            request = SearchInput.model_validate(input)
        except ValidationError as exc:
            raise ValueError("搜索输入无效") from exc
        terms = request.query.casefold().split()
        matches = [
            result for result in self._results
            if all(term in f"{result.title} {result.content}".casefold() for term in terms)
        ][: request.limit]
        return ToolResult(
            tool_name=self.name,
            output={
                "results": [
                    {"title": result.title, "content": result.content[:1000], **({"url": result.url} if result.url else {})}
                    for result in matches
                ]
            },
        )
