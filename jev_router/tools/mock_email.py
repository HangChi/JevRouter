from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from jev_router.tools.base import ToolResult


class MockEmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("to")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        local, separator, domain = value.rpartition("@")
        if not separator or not local or "." not in domain or any(char.isspace() for char in value):
            raise ValueError("recipient must be a valid email address")
        return value


class MockEmailTool:
    name = "send_mock_email"
    description = "Validate and simulate an email locally without sending it."
    risk = "external"

    def execute(self, input: dict[str, Any]) -> ToolResult:
        try:
            email = MockEmailInput.model_validate(input)
        except ValidationError as exc:
            raise ValueError("invalid mock email input") from exc
        return ToolResult(
            tool_name=self.name,
            output={"status": "simulated", "to": str(email.to), "subject": email.subject},
        )
