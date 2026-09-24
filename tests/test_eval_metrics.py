from __future__ import annotations

from evals.metrics import summarize
from evals.runner import CaseOutcome


def outcome(
    case_id: str = "case-1",
    *,
    mode: str = "jev",
    action: str | None = "calculator",
    expected: str = "calculator",
    allowed: tuple[str, ...] = ("calculator",),
    requires_confirmation: bool = False,
    policy_outcome: str | None = "execute",
    latency_ms: int = 100,
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    error: str | None = None,
) -> CaseOutcome:
    escalated = None if policy_outcome is None else policy_outcome in {
        "ask_confirmation",
        "delegate_to_llm",
        "ask_user",
    }
    confirmation_requested = None if policy_outcome is None else policy_outcome == "ask_confirmation"
    return CaseOutcome(
        case_id=case_id,
        goal="a goal",
        expected_action=expected,
        allowed_actions=allowed,
        requires_confirmation=requires_confirmation,
        mode=mode,
        action=action,
        matched_expected=action == expected,
        matched_allowed=action is not None and action in allowed,
        succeeded=(
            action in allowed
            and (confirmation_requested is None or confirmation_requested == requires_confirmation)
        ),
        policy_outcome=policy_outcome,
        escalated=escalated,
        confirmation_requested=confirmation_requested,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )


def test_empty_outcomes_produce_zeroed_metrics() -> None:
    metrics = summarize(())
    assert metrics.jev is None
    assert metrics.llm is None
    assert metrics.agreement_count is None
    assert metrics.compared_count is None
    assert metrics.agreement_rate is None
    assert metrics.disagreement_case_ids == ()


def test_single_perfect_jev_case() -> None:
    metrics = summarize([outcome()])
    jev = metrics.jev
    assert jev is not None
    assert jev.case_count == 1
    assert jev.error_count == 0
    assert jev.expected_match_count == 1
    assert jev.allowed_match_count == 1
    assert jev.success_count == 1
    assert jev.expected_match_rate == 1.0
    assert jev.allowed_match_rate == 1.0
    assert jev.success_rate == 1.0
    assert jev.error_rate == 0.0
    assert jev.escalation_count == 0
    assert jev.escalation_rate == 0.0
    assert jev.latency.mean_ms == 100.0
    assert jev.latency.p50_ms == 100
    assert jev.latency.p95_ms == 100
    assert jev.latency.max_ms == 100
    assert jev.input_tokens is not None
    assert (jev.input_tokens.mean, jev.input_tokens.total) == (10.0, 10)
    assert jev.output_tokens is not None
    assert (jev.output_tokens.mean, jev.output_tokens.total) == (5.0, 5)


def test_rates_are_computed_over_the_case_count() -> None:
    outcomes = [
        outcome("case-1"),
        outcome("case-2", action="web_search", expected="web_search", allowed=("web_search",)),
        outcome("case-3", action="finish"),
    ]
    jev = summarize(outcomes).jev
    assert jev is not None
    assert jev.expected_match_count == 2
    assert jev.allowed_match_count == 2
    assert jev.expected_match_rate == 2 / 3
    assert jev.success_count == 2
    assert jev.success_rate == 2 / 3


def test_escalation_and_confirmation_counts() -> None:
    outcomes = [
        outcome("case-1", policy_outcome="execute"),
        outcome("case-2", policy_outcome="ask_confirmation", requires_confirmation=True),
        # Two deliberate mismatches: a risky action executed without asking, and
        # a harmless action that asked anyway.
        outcome("case-3", policy_outcome="execute", requires_confirmation=True),
        outcome("case-4", policy_outcome="ask_confirmation"),
        outcome("case-5", policy_outcome="delegate_to_llm"),
        outcome("case-6", policy_outcome="finish"),
    ]
    jev = summarize(outcomes).jev
    assert jev is not None
    assert jev.escalation_count == 3
    assert jev.escalation_rate == 0.5
    assert jev.confirmation_expected_count == 2
    assert jev.confirmation_requested_count == 2
    assert jev.confirmation_match_count == 4


def test_llm_mode_has_no_policy_metrics() -> None:
    outcomes = [outcome("case-1", mode="llm", policy_outcome=None)]
    metrics = summarize(outcomes)
    assert metrics.jev is None
    llm = metrics.llm
    assert llm is not None
    assert llm.case_count == 1
    assert llm.escalation_count is None
    assert llm.escalation_rate is None
    assert llm.confirmation_requested_count is None
    assert llm.confirmation_match_count is None
    assert llm.success_count == 1


def test_errors_count_and_leave_tokens_absent() -> None:
    outcomes = [
        outcome("case-1", action=None, input_tokens=None, output_tokens=None, error="http: down"),
    ]
    jev = summarize(outcomes).jev
    assert jev is not None
    assert jev.error_count == 1
    assert jev.error_rate == 1.0
    assert jev.input_tokens is None
    assert jev.output_tokens is None
    # Latency is measured even when the call failed.
    assert jev.latency.mean_ms == 100.0


def test_token_stats_skip_cases_without_usage() -> None:
    outcomes = [
        outcome("case-1", input_tokens=10, output_tokens=4),
        outcome("case-2", input_tokens=None, output_tokens=None),
    ]
    jev = summarize(outcomes).jev
    assert jev is not None
    assert jev.input_tokens is not None
    assert (jev.input_tokens.mean, jev.input_tokens.total) == (10.0, 10)
    assert jev.output_tokens is not None
    assert (jev.output_tokens.mean, jev.output_tokens.total) == (4.0, 4)


def test_percentiles_use_nearest_rank() -> None:
    outcomes = [outcome(f"case-{index}", latency_ms=index) for index in range(1, 11)]
    latency = summarize(outcomes).jev
    assert latency is not None
    assert latency.latency.max_ms == 10
    assert latency.latency.mean_ms == 5.5
    # Nearest rank over 10 samples: p50 is the 5th, p95 the 10th.
    assert latency.latency.p50_ms == 5
    assert latency.latency.p95_ms == 10


def test_agreement_is_measured_over_paired_cases_only() -> None:
    outcomes = [
        outcome("case-1", mode="jev", action="calculator"),
        outcome("case-1", mode="llm", action="calculator"),
        outcome("case-2", mode="jev", action="web_search"),
        outcome("case-2", mode="llm", action="finish"),
        outcome("case-3", mode="jev", action=None, input_tokens=None, output_tokens=None, error="http: down"),
        outcome("case-3", mode="llm", action="calculator"),
    ]
    metrics = summarize(outcomes)
    assert metrics.compared_count == 2
    assert metrics.agreement_count == 1
    assert metrics.agreement_rate == 0.5
    assert metrics.disagreement_case_ids == ("case-2",)


def test_jev_only_run_has_no_agreement() -> None:
    metrics = summarize([outcome(mode="jev")])
    assert metrics.agreement_rate is None
    assert metrics.compared_count is None
