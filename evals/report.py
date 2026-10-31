from __future__ import annotations

from typing import Any

from evals.metrics import ComparisonMetrics, LatencyStats, ModeMetrics, TokenStats
from evals.runner import EvalReport

REPORT_VERSION = 1


def report_to_dict(report: EvalReport) -> dict[str, Any]:
    """把一份报告序列化成 API 记录的版本化信封。

    各比率是显式写出来的，而不是留给派生属性：落库后的报告要能自我描述，
    以后再读它不应该依赖当时那个版本的算术。
    """
    return {
        "version": REPORT_VERSION,
        "data": {
            "run_id": report.run_id,
            "mode": report.mode,
            "created_at": report.created_at,
            "outcomes": [
                {
                    "case_id": outcome.case_id,
                    "goal": outcome.goal,
                    "expected_action": outcome.expected_action,
                    "allowed_actions": list(outcome.allowed_actions),
                    "requires_confirmation": outcome.requires_confirmation,
                    "mode": outcome.mode,
                    "action": outcome.action,
                    "matched_expected": outcome.matched_expected,
                    "matched_allowed": outcome.matched_allowed,
                    "succeeded": outcome.succeeded,
                    "policy_outcome": outcome.policy_outcome,
                    "escalated": outcome.escalated,
                    "confirmation_requested": outcome.confirmation_requested,
                    "latency_ms": outcome.latency_ms,
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "error": outcome.error,
                    "confidence": outcome.confidence,
                    "risk": outcome.risk,
                    "requires_confirmation_probability": (
                        outcome.requires_confirmation_probability
                    ),
                    "needs_reasoning_probability": outcome.needs_reasoning_probability,
                    "tool_risk": outcome.tool_risk,
                }
                for outcome in report.outcomes
            ],
            "metrics": _metrics_to_dict(report.metrics),
        },
    }



def _metrics_to_dict(metrics: ComparisonMetrics) -> dict[str, Any]:
    return {
        "jev": None if metrics.jev is None else _mode_to_dict(metrics.jev),
        "llm": None if metrics.llm is None else _mode_to_dict(metrics.llm),
        "agreement_count": metrics.agreement_count,
        "compared_count": metrics.compared_count,
        "agreement_rate": metrics.agreement_rate,
        "disagreement_case_ids": list(metrics.disagreement_case_ids),
    }


def _mode_to_dict(metrics: ModeMetrics) -> dict[str, Any]:
    return {
        "mode": metrics.mode,
        "case_count": metrics.case_count,
        "error_count": metrics.error_count,
        "expected_match_count": metrics.expected_match_count,
        "allowed_match_count": metrics.allowed_match_count,
        "success_count": metrics.success_count,
        "escalation_count": metrics.escalation_count,
        "confirmation_expected_count": metrics.confirmation_expected_count,
        "confirmation_requested_count": metrics.confirmation_requested_count,
        "confirmation_match_count": metrics.confirmation_match_count,
        "expected_match_rate": metrics.expected_match_rate,
        "allowed_match_rate": metrics.allowed_match_rate,
        "success_rate": metrics.success_rate,
        "error_rate": metrics.error_rate,
        "escalation_rate": metrics.escalation_rate,
        "latency": _latency_to_dict(metrics.latency),
        "input_tokens": _tokens_to_dict(metrics.input_tokens),
        "output_tokens": _tokens_to_dict(metrics.output_tokens),
    }


def _latency_to_dict(latency: LatencyStats) -> dict[str, Any]:
    return {
        "mean_ms": latency.mean_ms,
        "p50_ms": latency.p50_ms,
        "p95_ms": latency.p95_ms,
        "max_ms": latency.max_ms,
    }


def _tokens_to_dict(tokens: TokenStats | None) -> dict[str, Any] | None:
    if tokens is None:
        return None
    return {"mean": tokens.mean, "total": tokens.total}
