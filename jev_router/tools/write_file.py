from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jev_router.tools.base import ToolResult


class WriteFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=1_000_000)


class WriteFileTool:
    name = "write_file"
    description = "Write a bounded text file under a configured root directory."
    risk = "write"

    def __init__(self, root: str | Path, *, allow_overwrite: bool = False, max_bytes: int = 1_000_000) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._allow_overwrite = allow_overwrite
        self._max_bytes = max_bytes

    def execute(self, input: dict[str, Any]) -> ToolResult:
        try:
            request = WriteFileInput.model_validate(input)
        except ValidationError as exc:
            raise ValueError("invalid file write input") from exc
        relative = Path(request.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("file path must stay within the configured root")
        destination = self._root / relative
        resolved = destination.resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("file path must stay within the configured root") from exc
        content = request.content.encode("utf-8")
        if len(content) > self._max_bytes:
            raise ValueError("file content exceeds the configured size limit")
        if resolved.exists() and not self._allow_overwrite:
            raise ValueError("overwriting an existing file is not allowed")
        if resolved.exists() and not resolved.is_file():
            raise ValueError("destination must be a regular file")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("file path must stay within the configured root") from exc
        if not self._allow_overwrite:
            try:
                with resolved.open("xb") as handle:
                    handle.write(content)
            except FileExistsError as exc:
                raise ValueError("overwriting an existing file is not allowed") from exc
        else:
            with resolved.open("wb") as handle:
                handle.write(content)
        return ToolResult(tool_name=self.name, output={"path": str(relative), "bytes_written": len(content)})
