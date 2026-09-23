from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jev_router.tools.base import ToolResult


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class SearchDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    url: str | None = None


class KnowledgeSearchTool:
    name = "knowledge_search"
    description = "Search an injected set of local knowledge documents."
    risk = "read"

    def __init__(self, documents: Sequence[SearchDocument | dict[str, Any]]) -> None:
        self._documents = tuple(SearchDocument.model_validate(doc) for doc in documents)

    def execute(self, input: dict[str, Any]) -> ToolResult:
        try:
            request = SearchInput.model_validate(input)
        except ValidationError as exc:
            raise ValueError("invalid search input") from exc
        terms = request.query.casefold().split()
        matches = [
            doc for doc in self._documents
            if all(term in f"{doc.title} {doc.content}".casefold() for term in terms)
        ][: request.limit]
        return ToolResult(
            tool_name=self.name,
            output={
                "results": [
                    {"title": doc.title, "content": doc.content[:1000], **({"url": doc.url} if doc.url else {})}
                    for doc in matches
                ]
            },
        )
