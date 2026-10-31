from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from evals.report import REPORT_VERSION
from evals.runner import CaseOutcome
from jev_router.policy import PolicyEngine, PolicyThresholds
from jev_router.router import RouteDecision
from jev_router.tools.registry import ToolRegistry

# 评分权重不是客观真理，而是一个明确的偏好声明：把正确的动作自动执行掉是收益，
# 把错误的动作自动执行掉是这次校准里唯一真正危险的事件，因此重罚；请人工确认一个
# 错误的动作仍有成本（浪费一次注意力），但比机器直接做错要轻。
EXECUTED_CORRECT_WEIGHT = 1.0
EXECUTED_WRONG_WEIGHT = -2.0
CONFIRMED_WRONG_WEIGHT = -0.5


@dataclass(frozen=True)
class CalibrationRow:
    """一组阈值在全部用例上的回放结果。"""

    thresholds: PolicyThresholds
    executed: int
    confirmed: int
    delegated: int
    executed_correct: int
    executed_wrong: int
    confirmed_wrong: int
    confirmation_mismatches: int
    matched_allowed: int
    scored_cases: int

    @property
    def score(self) -> float:
        return (
            self.executed_correct * EXECUTED_CORRECT_WEIGHT
            + self.executed_wrong * EXECUTED_WRONG_WEIGHT
            + self.confirmed_wrong * CONFIRMED_WRONG_WEIGHT
        )

    @property
    def escalation_rate(self) -> float:
        return _rate(self.delegated, self.scored_cases)

    @property
    def execute_rate(self) -> float:
        return _rate(self.executed, self.scored_cases)

    def rank_key(self) -> tuple[float, int, int, float, float, float, float]:
        """先看分数，再少打扰人，最后少花账；全平手时偏向更保守的一侧。

        注意「保守」在两个方向上不是同一个符号：
        - 置信度与推理阈值越高，越多步骤交给 LLM，自动执行面越小；
        - 确认与风险阈值越低，越多动作要求人工批准，自动执行面同样越小。

        同分时选自动执行面更小的那一侧，是因为数据只能说明「这批用例上没差别」，
        说明不了「多放开一点也不会出事」。之前四个维度一律取高，等于把确认和风险
        两个安全阀悄悄关掉，而它们恰恰是越低越安全。
        """
        return (
            -self.score,
            self.confirmation_mismatches,
            self.delegated,
            self.thresholds.confirmation,
            self.thresholds.risk,
            -self.thresholds.reasoning,
            -self.thresholds.confidence,
        )


@dataclass(frozen=True)
class CalibrationResult:
    case_count: int
    skipped_count: int
    rows: tuple[CalibrationRow, ...]
    at_boundary: tuple[str, ...] = ()
    inert_dimensions: tuple[str, ...] = ()

    @property
    def best(self) -> CalibrationRow | None:
        return self.rows[0] if self.rows else None


def default_grid() -> tuple[PolicyThresholds, ...]:
    """默认搜索网格：粗到足以看趋势，细到不至于把一次评测榨成过拟合。

    置信度按 0.05 取步长，是为了让当前默认值 ``0.75`` 落在网格上——否则
    「推荐阈值」永远无法指向「什么都不改」这个结论。
    """
    rows: list[PolicyThresholds] = []
    for confirmation in _steps(0.50, 0.95, 0.05):
        for risk in _steps(1.5, 3.5, 0.5):
            for reasoning in _steps(0.50, 0.90, 0.10):
                for confidence in _steps(0.50, 0.90, 0.05):
                    rows.append(
                        PolicyThresholds(
                            confirmation=round(confirmation, 2),
                            risk=round(risk, 2),
                            reasoning=round(reasoning, 2),
                            confidence=round(confidence, 2),
                        )
                    )
    return tuple(rows)


def replayable(outcomes: Iterable[CaseOutcome]) -> list[CaseOutcome]:
    """能离线重放的用例：有完整信号、没有报错、且来自 Jev 路由层。

    LLM 基线没有概率，也就没有可重放的策略输入；缺信号的旧报告同理。
    """
    return [
        outcome
        for outcome in outcomes
        if outcome.mode == "jev"
        and outcome.error is None
        and outcome.action is not None
        and outcome.confidence is not None
        and outcome.risk is not None
        and outcome.requires_confirmation_probability is not None
        and outcome.needs_reasoning_probability is not None
    ]


def calibrate(
    outcomes: Sequence[CaseOutcome],
    tools: ToolRegistry,
    *,
    grid: Sequence[PolicyThresholds] | None = None,
) -> CalibrationResult:
    """在已记录的信号上重放策略引擎，为每一组阈值算一份成绩。

    重放用的是生产代码里那个 ``PolicyEngine``，不是这里另写一份判断逻辑——
    校准如果自己实现一遍策略，它校准的就是另一个人写的策略。
    """
    usable = replayable(outcomes)
    skipped = sum(1 for outcome in outcomes if outcome.mode == "jev") - len(usable)
    candidates = grid if grid is not None else default_grid()
    rows = [score_row(usable, tools, thresholds) for thresholds in candidates]
    rows.sort(key=CalibrationRow.rank_key)
    best = rows[0] if rows else None
    return CalibrationResult(
        case_count=len(usable),
        skipped_count=skipped,
        rows=tuple(rows),
        at_boundary=() if best is None else _boundary_dimensions(best, candidates),
        inert_dimensions=(
            () if best is None else _inert_dimensions(best, usable, tools, candidates)
        ),
    )


def _inert_dimensions(
    best: CalibrationRow,
    usable: Sequence[CaseOutcome],
    tools: ToolRegistry,
    candidates: Sequence[PolicyThresholds],
) -> tuple[str, ...]:
    """在最优解附近怎么调都不会改变结果的维度。

    这类维度的「推荐值」只是同分里任取的一个，改它没有任何数据支撑。承认这一点
    比打印一组看起来很确定的数字有用——否则读的人会把「网格内最好」当成「应该这么改」。
    """
    inert: list[str] = []
    for name in best.thresholds.as_dict():
        axis = sorted({getattr(candidate, name) for candidate in candidates})
        if len(axis) < 2:
            continue
        scores = {
            score_row(usable, tools, replace(best.thresholds, **{name: value})).score
            for value in axis
        }
        if len(scores) == 1:
            inert.append(name)
    return tuple(inert)


def _boundary_dimensions(
    best: CalibrationRow, candidates: Sequence[PolicyThresholds]
) -> tuple[str, ...]:
    """哪些维度上的最优值正好落在搜索范围的边沿。

    落在边沿说明真实最优可能在范围之外——这时给出的数字仍然可用，但它
    说明的是「在当前搜索空间里最好」，不能当成「已经找到最优点」。
    """
    hit: list[str] = []
    values = best.thresholds.as_dict()
    for name, value in values.items():
        axis = {getattr(candidate, name) for candidate in candidates}
        # 只有一个候选值的维度是「被固定住」，不是「取到了边沿」——两者含义不同。
        if len(axis) < 2:
            continue
        if value <= min(axis) or value >= max(axis):
            hit.append(name)
    return tuple(hit)


def score_row(
    usable: Sequence[CaseOutcome],
    tools: ToolRegistry,
    thresholds: PolicyThresholds,
) -> CalibrationRow:
    engine = PolicyEngine(tools, thresholds)
    executed = confirmed = delegated = 0
    executed_correct = executed_wrong = confirmed_wrong = 0
    mismatches = matched_allowed = 0
    for outcome in usable:
        decision = engine.evaluate(_route_of(outcome))
        matched = outcome.action in outcome.allowed_actions
        matched_allowed += 1 if matched else 0
        requested = decision.outcome == "ask_confirmation"
        if requested != outcome.requires_confirmation:
            mismatches += 1
        if decision.outcome == "execute":
            executed += 1
            if matched:
                executed_correct += 1
            else:
                executed_wrong += 1
        elif decision.outcome == "ask_confirmation":
            confirmed += 1
            if not matched:
                confirmed_wrong += 1
        elif decision.outcome in ("delegate_to_llm", "ask_user"):
            delegated += 1
    return CalibrationRow(
        thresholds=thresholds,
        executed=executed,
        confirmed=confirmed,
        delegated=delegated,
        executed_correct=executed_correct,
        executed_wrong=executed_wrong,
        confirmed_wrong=confirmed_wrong,
        confirmation_mismatches=mismatches,
        matched_allowed=matched_allowed,
        scored_cases=len(usable),
    )


def _route_of(outcome: CaseOutcome) -> RouteDecision:
    return RouteDecision(
        action=outcome.action or "",
        confidence=outcome.confidence or 0.0,
        risk=outcome.risk or 0.0,
        risk_confidence=0.0,
        requires_confirmation=outcome.requires_confirmation_probability or 0.0,
        needs_reasoning=outcome.needs_reasoning_probability or 0.0,
        model="calibration-replay",
    )


def _steps(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 4))
        current += step
    return values


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


_REQUIRED_FIELDS = frozenset(
    {
        "case_id",
        "goal",
        "expected_action",
        "allowed_actions",
        "requires_confirmation",
        "mode",
        "matched_expected",
        "matched_allowed",
        "succeeded",
        "latency_ms",
    }
)


def load_outcomes(path: str | Path) -> tuple[CaseOutcome, ...]:
    """从一份 ``--json-out`` 报告里读回用例记录。

    字段集合必须与 ``CaseOutcome`` 对得上：多出来的键说明报告来自另一个版本，
    与其猜它的含义，不如直接拒绝并让人看一眼。
    """
    location = Path(path)
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"报告文件不存在：{location}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"报告文件不是合法 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("报告文件必须是一个 JSON 对象")
    if raw.get("version") != REPORT_VERSION:
        raise ValueError(
            f"报告版本 {raw.get('version')!r} 不受支持，本版本读取 {REPORT_VERSION}"
        )
    data = raw.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("outcomes"), list):
        raise TypeError("报告里没有 outcomes 列表")
    names = {field.name for field in fields(CaseOutcome)}
    outcomes: list[CaseOutcome] = []
    for index, entry in enumerate(data["outcomes"]):
        if not isinstance(entry, dict):
            raise TypeError(f"第 {index} 条用例记录不是对象")
        unknown = set(entry) - names
        if unknown:
            raise ValueError(
                f"第 {index} 条用例记录含有未知字段：{', '.join(sorted(unknown))}"
            )
        missing = _REQUIRED_FIELDS - set(entry)
        if missing:
            raise ValueError(
                f"第 {index} 条用例记录缺少字段：{', '.join(sorted(missing))}"
            )
        outcomes.append(_outcome_of(entry))
    return tuple(outcomes)


def _outcome_of(entry: dict[str, Any]) -> CaseOutcome:
    values: dict[str, Any] = dict(entry)
    values["allowed_actions"] = tuple(values["allowed_actions"])
    return CaseOutcome(**values)

