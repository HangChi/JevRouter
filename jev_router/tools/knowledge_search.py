from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jev_router.tools.base import RiskLevel, ToolResult


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "The search terms; every term must appear in a document for it to match."
        ),
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="How many results to return at most.",
    )


class SearchDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    url: str | None = None


class KnowledgeSearchTool:
    name = "knowledge_search"
    # 描述的是「什么时候用它」，不是它的实现方式。早先的写法只说
    # "injected set of local knowledge documents"，等于把实现细节当成能力说明，
    # 模型无从判断「公司假期有几天」这类问题该落到这里，于是转向 ask_user。
    description = (
        "Search the organization's own knowledge base: documented policies, "
        "procedures and reference facts. Use it when the goal asks about "
        "something the organization has already written down, as opposed to "
        "something to compute, to look up on the public web, or to create."
    )
    risk: RiskLevel = "read"
    input_model: type[BaseModel] = SearchInput

    def __init__(self, documents: Sequence[SearchDocument | dict[str, Any]]) -> None:
        self._documents = tuple(SearchDocument.model_validate(doc) for doc in documents)

    def execute(self, input: dict[str, Any]) -> ToolResult:
        try:
            request = SearchInput.model_validate(input)
        except ValidationError as exc:
            raise ValueError("搜索输入无效") from exc
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
