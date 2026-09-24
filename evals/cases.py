from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CASE_FILE_VERSION = 1

DEFAULT_CASES_PATH = Path(__file__).with_name("cases.json")


class CaseFileError(ValueError):
    """The case file cannot be used as it is."""


class EvalCase(BaseModel):
    """One routing expectation.

    ``expected_action`` is the action the project considers correct for the first
    step; ``allowed_actions`` is the set a router may choose from and still count
    as acceptable. ``requires_confirmation`` records whether the Policy Engine is
    expected to ask before acting — true exactly for the ``write``/``external``
    risk tools, mirroring the rule the Runner enforces at execution time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    goal: str = Field(min_length=1, max_length=2000)
    expected_action: str = Field(min_length=1, max_length=64)
    allowed_actions: tuple[str, ...] = Field(min_length=1)
    requires_confirmation: bool = False
    context: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("expected_action", "allowed_actions")
    @classmethod
    def _trimmed(cls, value: Any) -> Any:
        values = value if isinstance(value, tuple) else (value,)
        for item in values:
            if not isinstance(item, str) or not item.strip() or item.strip() != item:
                raise ValueError("action names must be non-empty and trimmed")
        return value

    @model_validator(mode="after")
    def _expected_is_allowed(self) -> EvalCase:
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("allowed_actions must not repeat")
        if self.expected_action not in self.allowed_actions:
            raise ValueError("expected_action must be one of allowed_actions")
        return self


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> tuple[EvalCase, ...]:
    """Read a versioned case file into validated cases.

    An unknown version, a malformed entry or a duplicate id is refused rather
    than skipped: a silently dropped case would change every rate the run
    reports.
    """
    location = Path(path)
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CaseFileError(f"case file does not exist: {location}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CaseFileError(f"case file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise CaseFileError("the case file must contain a JSON object")
    version = raw.get("version")
    if version != CASE_FILE_VERSION:
        raise CaseFileError(
            f"case file version {version!r} is not supported; this build reads {CASE_FILE_VERSION}"
        )
    entries = raw.get("cases")
    if not isinstance(entries, list) or not entries:
        raise CaseFileError("the case file must contain at least one case")
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        try:
            case = EvalCase.model_validate(entry)
        except ValidationError as exc:
            raise CaseFileError(f"case #{index} is invalid: {exc}") from exc
        if case.id in seen:
            raise CaseFileError(f"duplicate case id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return tuple(cases)
