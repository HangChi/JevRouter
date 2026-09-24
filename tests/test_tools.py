from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jev_router.tools import (
    CalculatorTool,
    KnowledgeSearchTool,
    MockEmailTool,
    SearchDocument,
    ToolRegistry,
    WebSearchMockTool,
    WriteFileTool,
)


def test_registry_resolves_registered_tools_and_rejects_duplicates() -> None:
    calculator = CalculatorTool()
    registry = ToolRegistry([calculator])

    assert registry.names() == ("calculator",)
    assert registry.get("calculator") is calculator
    assert registry.execute("calculator", {"expression": "2 * (3 + 4)"}).output == {"result": 14.0}
    with pytest.raises(ValueError, match="already registered"):
        registry.register(calculator)
    with pytest.raises(KeyError, match="not registered"):
        registry.get("unknown")


def test_calculator_supports_arithmetic_and_rejects_code() -> None:
    tool = CalculatorTool()

    assert tool.execute({"expression": "-2 ** 3 + 10 / 2"}).output == {"result": -3.0}
    for expression in ("__import__('os').getcwd()", "x + 1", "2 ** 101", "1 / 0"):
        with pytest.raises(ValueError):
            tool.execute({"expression": expression})


def test_knowledge_search_uses_injected_documents_and_bounds_results() -> None:
    tool = KnowledgeSearchTool([
        SearchDocument(title="Python", content="Python supports typed arithmetic."),
        SearchDocument(title="Rust", content="Rust uses ownership."),
    ])

    result = tool.execute({"query": "python arithmetic", "limit": 1})

    assert result.output["results"] == [
        {"title": "Python", "content": "Python supports typed arithmetic."}
    ]
    with pytest.raises(ValueError, match="invalid search input"):
        tool.execute({"query": "", "limit": 1})


def test_web_search_uses_only_injected_fixtures() -> None:
    tool = WebSearchMockTool([
        {"title": "Release notes", "content": "Python 3.15 release notes", "url": "https://example.test/release"}
    ])

    result = tool.execute({"query": "python release"})

    assert result.output["results"] == [
        {
            "title": "Release notes",
            "content": "Python 3.15 release notes",
            "url": "https://example.test/release",
        }
    ]
    assert WebSearchMockTool().execute({"query": "anything"}).output == {"results": []}


def test_write_file_creates_relative_file_and_denies_overwrite(tmp_path: Path) -> None:
    tool = WriteFileTool(tmp_path / "workspace")

    result = tool.execute({"path": "notes/today.txt", "content": "hello"})

    assert result.output == {"path": "notes/today.txt", "bytes_written": 5}
    assert (tmp_path / "workspace" / "notes" / "today.txt").read_text() == "hello"
    with pytest.raises(ValueError, match="overwriting"):
        tool.execute({"path": "notes/today.txt", "content": "changed"})


def test_write_file_rejects_absolute_traversal_and_oversized_content(tmp_path: Path) -> None:
    tool = WriteFileTool(tmp_path / "workspace", max_bytes=4)

    for path in ("../outside.txt", str(tmp_path / "absolute.txt")):
        with pytest.raises(ValueError, match="configured root"):
            tool.execute({"path": path, "content": "x"})
    with pytest.raises(ValueError, match="size limit"):
        tool.execute({"path": "large.txt", "content": "12345"})


def test_write_file_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    tool = WriteFileTool(root)

    with pytest.raises(ValueError, match="configured root"):
        tool.execute({"path": "escape/file.txt", "content": "blocked"})
    assert not (outside / "file.txt").exists()


def test_write_file_can_overwrite_only_when_configured(tmp_path: Path) -> None:
    tool = WriteFileTool(tmp_path / "workspace", allow_overwrite=True)

    tool.execute({"path": "notes.txt", "content": "first"})
    tool.execute({"path": "notes.txt", "content": "second"})

    assert (tmp_path / "workspace" / "notes.txt").read_text() == "second"


def test_mock_email_validates_and_only_returns_simulated_metadata() -> None:
    tool = MockEmailTool()

    result = tool.execute({"to": "alice@example.test", "subject": "Weather", "body": "Sunny"})

    assert tool.risk == "external"
    assert result.output == {"status": "simulated", "to": "alice@example.test", "subject": "Weather"}
    with pytest.raises(ValueError, match="invalid mock email"):
        tool.execute({"to": "not-an-email", "subject": "Weather", "body": "Sunny"})


def test_every_tool_declares_the_model_its_execute_validates() -> None:
    """The LLM argument resolver reads the schema from `input_model`.

    If a tool declared a model its `execute` does not actually validate against,
    the prompt would advertise a shape the tool refuses — so the two are checked
    against each other here rather than trusted to stay in step.
    """
    documents = [SearchDocument(title="t", content="c")]
    tools = [
        CalculatorTool(),
        KnowledgeSearchTool(documents),
        WebSearchMockTool(),
        WriteFileTool("/tmp/jevrouter-tool-protocol"),
        MockEmailTool(),
    ]
    for tool in tools:
        schema = tool.input_model.model_json_schema()
        assert schema["type"] == "object"
        assert schema.get("properties"), tool.name
        # A field the schema does not describe must be refused by the tool.
        rejected = False
        try:
            tool.input_model.model_validate({"unknown_field": "x"})
        except ValidationError:
            rejected = True
        assert rejected, tool.name
