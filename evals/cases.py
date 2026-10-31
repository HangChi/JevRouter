from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CASE_FILE_VERSION = 1

DEFAULT_CASES_PATH = Path(__file__).with_name("cases.json")


class CaseFileError(ValueError):
    """用例文件无法按原样使用。"""


class EvalCase(BaseModel):
    """一条路由期望。

    ``expected_action`` 是项目认为该用例第一步正确的动作；``allowed_actions``
    是路由层可以从中选择、且仍算可接受的动作集合。``requires_confirmation``
    记录策略引擎是否应先行询问 —— 恰好对 ``write``/``external`` 风险的工具为
    true，与 Runner 在执行期强制的规则保持一致。
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
                raise ValueError("动作名必须非空且不含首尾空白")
        return value

    @model_validator(mode="after")
    def _expected_is_allowed(self) -> EvalCase:
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("allowed_actions 不得重复")
        if self.expected_action not in self.allowed_actions:
            raise ValueError("expected_action 必须是 allowed_actions 之一")
        return self


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> tuple[EvalCase, ...]:
    """把一份带版本号的用例文件读成经过校验的用例。

    未知版本、格式错误的条目或重复的 id 都会被直接拒绝，而不是跳过：
    静默丢掉一个用例会改变这次运行报告的每一项比率。
    """
    location = Path(path)
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CaseFileError(f"用例文件不存在：{location}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CaseFileError(f"用例文件不是合法的 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise CaseFileError("用例文件必须包含一个 JSON 对象")
    version = raw.get("version")
    if version != CASE_FILE_VERSION:
        raise CaseFileError(
            f"用例文件版本 {version!r} 不受支持；本构建读取版本 {CASE_FILE_VERSION}"
        )
    entries = raw.get("cases")
    if not isinstance(entries, list) or not entries:
        raise CaseFileError("用例文件必须至少包含一个用例")
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        try:
            case = EvalCase.model_validate(entry)
        except ValidationError as exc:
            raise CaseFileError(f"用例 #{index} 无效：{exc}") from exc
        if case.id in seen:
            raise CaseFileError(f"重复的用例 id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return tuple(cases)
