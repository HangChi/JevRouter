from __future__ import annotations

from pathlib import Path

from jev_router.tools import (
    CalculatorTool,
    KnowledgeSearchTool,
    MockEmailTool,
    SearchDocument,
    ToolRegistry,
    WebSearchMockTool,
    WriteFileTool,
)

# Fixed fixtures so a run is reproducible: the eval measures routing, and the
# candidate descriptions come from the registry, not from the data behind it.
KNOWLEDGE_FIXTURES: tuple[SearchDocument, ...] = (
    SearchDocument(
        title="Travel policy",
        content="Daily meal allowance is 500 CNY; hotels are reimbursed up to 600 CNY per night.",
    ),
    SearchDocument(
        title="API rate limits",
        content="The public API allows 600 requests per minute per key, with a burst of 60.",
    ),
    SearchDocument(
        title="Onboarding checklist",
        content="New hires complete account setup, security training, team intro and first project.",
    ),
    SearchDocument(
        title="Enterprise pricing",
        content="The enterprise plan is 2400 CNY per seat per year with a minimum of twenty seats.",
    ),
    SearchDocument(
        title="Refund policy",
        content="Refunds are available within 14 days of purchase for unused seats.",
    ),
    SearchDocument(
        title="Backup schedule",
        content="Databases are backed up every six hours and retained for 30 days.",
    ),
    SearchDocument(
        title="Service level agreement",
        content="We commit to 99.9% monthly availability for paid plans.",
    ),
    SearchDocument(
        title="Leave policy",
        content="Full-time employees accrue 15 days of paid annual leave per year.",
    ),
)

WEB_FIXTURES: tuple[SearchDocument, ...] = (
    SearchDocument(
        title="Tokyo weather tomorrow",
        content="Tomorrow in Tokyo: rain, 24C high and 19C low, with a 70% chance of showers.",
        url="https://example.invalid/tokyo-weather",
    ),
    SearchDocument(
        title="Python release notes",
        content="The latest stable Python release adds performance improvements and new typing features.",
        url="https://example.invalid/python-release",
    ),
    SearchDocument(
        title="Exchange rates",
        content="USD to CNY is quoted at 7.18 in the latest update.",
        url="https://example.invalid/fx",
    ),
)


def default_registry(workspace_root: str | Path) -> ToolRegistry:
    """The five MVP tools with fixed fixtures, rooted at a caller-owned directory."""
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    return ToolRegistry(
        [
            CalculatorTool(),
            KnowledgeSearchTool(KNOWLEDGE_FIXTURES),
            WebSearchMockTool(WEB_FIXTURES),
            WriteFileTool(root),
            MockEmailTool(),
        ]
    )
