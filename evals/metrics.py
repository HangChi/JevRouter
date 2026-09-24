from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # breaks the import cycle: the runner imports the aggregation
    from evals.runner import CaseOutcome

JEVMODE = "jev"
LLMMODE = "llm"


@dataclass(frozen=True)
class LatencyStats:
    """Millisecond statistics over one mode's cases.

    Percentiles use the nearest-rank method: the p95 of 50 samples is the 48th
    value in sorted order. It is deliberately simple — these numbers compare
    modes against each other, not against a specification.
    """

    mean_ms: float
    p50_ms: int
    p95_ms: int
    max_ms: int


@dataclass(frozen=True)
class TokenStats:
    mean: float
    total: int


@dataclass(frozen=True)
class ModeMetrics:
    """Everything one router did across the case set.

    Policy fields are ``None`` for the LLM baseline: it produces no probabilities,
    so it has no policy outcome to escalate or confirm. Reporting that as zero
    would claim a fact the baseline cannot have.
    """

    mode: str
    case_count: int
    error_count: int
    expected_match_count: int
    allowed_match_count: int
    success_count: int
    escalation_count: int | None
    confirmation_expected_count: int | None
    confirmation_requested_count: int | None
    confirmation_match_count: int | None
    latency: LatencyStats
    input_tokens: TokenStats | None
    output_tokens: TokenStats | None

    @property
    def expected_match_rate(self) -> float:
        return _rate(self.expected_match_count, self.case_count)

    @property
    def allowed_match_rate(self) -> float:
        return _rate(self.allowed_match_count, self.case_count)

    @property
    def success_rate(self) -> float:
        return _rate(self.success_count, self.case_count)

    @property
    def error_rate(self) -> float:
        return _rate(self.error_count, self.case_count)

    @property
    def escalation_rate(self) -> float | None:
        if self.escalation_count is None:
            return None
        return _rate(self.escalation_count, self.case_count)


@dataclass(frozen=True)
class ComparisonMetrics:
    """Per-mode metrics plus how often the two routers agreed.

    ``agreement_rate`` is ``None`` unless both modes answered at least one case,
    because "0%" and "never compared" are different statements.
    """

    jev: ModeMetrics | None
    llm: ModeMetrics | None
    agreement_count: int | None
    compared_count: int | None
    disagreement_case_ids: tuple[str, ...]

    @property
    def agreement_rate(self) -> float | None:
        if self.agreement_count is None or not self.compared_count:
            return None
        return _rate(self.agreement_count, self.compared_count)


def summarize(outcomes: Sequence[CaseOutcome]) -> ComparisonMetrics:
    jev_outcomes = [outcome for outcome in outcomes if outcome.mode == JEVMODE]
    llm_outcomes = [outcome for outcome in outcomes if outcome.mode == LLMMODE]
    jev = _mode_metrics(JEVMODE, jev_outcomes) if jev_outcomes else None
    llm = _mode_metrics(LLMMODE, llm_outcomes) if llm_outcomes else None
    agreement_count: int | None = None
    compared_count: int | None = None
    disagreements: list[str] = []
    if jev_outcomes and llm_outcomes:
        llm_by_case = {outcome.case_id: outcome for outcome in llm_outcomes}
        pairs = [
            (jev_outcome, llm_by_case[jev_outcome.case_id])
            for jev_outcome in jev_outcomes
            if jev_outcome.case_id in llm_by_case
            and jev_outcome.action is not None
            and llm_by_case[jev_outcome.case_id].action is not None
        ]
        compared_count = len(pairs)
        agreement_count = sum(1 for left, right in pairs if left.action == right.action)
        disagreements = sorted(
            left.case_id for left, right in pairs if left.action != right.action
        )
    return ComparisonMetrics(
        jev=jev,
        llm=llm,
        agreement_count=agreement_count,
        compared_count=compared_count,
        disagreement_case_ids=tuple(disagreements),
    )


def _mode_metrics(mode: str, outcomes: Sequence[CaseOutcome]) -> ModeMetrics:
    count = len(outcomes)
    errors = sum(1 for outcome in outcomes if outcome.error is not None)
    escalation = [outcome for outcome in outcomes if outcome.escalated is not None]
    confirmations = [outcome for outcome in outcomes if outcome.confirmation_requested is not None]
    expected_confirmations = sum(
        1 for outcome in confirmations if outcome.requires_confirmation
    )
    return ModeMetrics(
        mode=mode,
        case_count=count,
        error_count=errors,
        expected_match_count=sum(1 for outcome in outcomes if outcome.matched_expected),
        allowed_match_count=sum(1 for outcome in outcomes if outcome.matched_allowed),
        success_count=sum(1 for outcome in outcomes if outcome.succeeded),
        escalation_count=(sum(1 for outcome in escalation if outcome.escalated) if escalation else None),
        confirmation_expected_count=(expected_confirmations if confirmations else None),
        confirmation_requested_count=(
            sum(1 for outcome in confirmations if outcome.confirmation_requested) if confirmations else None
        ),
        confirmation_match_count=(
            sum(
                1
                for outcome in confirmations
                if outcome.confirmation_requested == outcome.requires_confirmation
            )
            if confirmations
            else None
        ),
        latency=_latency([outcome.latency_ms for outcome in outcomes]),
        input_tokens=_tokens([outcome.input_tokens for outcome in outcomes]),
        output_tokens=_tokens([outcome.output_tokens for outcome in outcomes]),
    )


def _latency(samples: Sequence[int]) -> LatencyStats:
    if not samples:
        return LatencyStats(mean_ms=0.0, p50_ms=0, p95_ms=0, max_ms=0)
    ordered = sorted(samples)
    return LatencyStats(
        mean_ms=math.fsum(ordered) / len(ordered),
        p50_ms=_percentile(ordered, 50),
        p95_ms=_percentile(ordered, 95),
        max_ms=ordered[-1],
    )


def _percentile(ordered: Sequence[int], percent: int) -> int:
    rank = max(1, math.ceil(percent / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _tokens(values: Sequence[int | None]) -> TokenStats | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return TokenStats(mean=math.fsum(present) / len(present), total=sum(present))

def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0
