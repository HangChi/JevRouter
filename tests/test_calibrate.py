from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evals.calibrate import (
    CalibrationRow,
    calibrate,
    default_grid,
    load_outcomes,
    replayable,
)
from evals.cli import EXIT_CONFIGURATION, EXIT_OK, main
from evals.metrics import summarize
from evals.report import report_to_dict
from evals.runner import CaseOutcome, EvalReport
from jev_router.policy import PolicyThresholds
from jev_router.tools import (
    CalculatorTool,
    MockEmailTool,
    ToolRegistry,
    WriteFileTool,
)


def registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(
        [
            CalculatorTool(),
            WriteFileTool(tmp_path / "workspace"),
            MockEmailTool(),
        ]
    )


def outcome(
    *,
    case_id: str = "calc-001",
    action: str = "calculator",
    allowed: tuple[str, ...] = ("calculator",),
    requires_confirmation: bool = False,
    confidence: float = 0.9,
    risk: float = 0.5,
    confirmation_probability: float = 0.1,
    reasoning_probability: float = 0.1,
    mode: str = "jev",
    error: str | None = None,
) -> CaseOutcome:
    return CaseOutcome(
        case_id=case_id,
        goal="随便一个目标",
        expected_action=allowed[0],
        allowed_actions=allowed,
        requires_confirmation=requires_confirmation,
        mode=mode,
        action=action,
        matched_expected=True,
        matched_allowed=action in allowed,
        succeeded=True,
        policy_outcome=None,
        escalated=None,
        confirmation_requested=None,
        latency_ms=10,
        input_tokens=None,
        output_tokens=None,
        error=error,
        confidence=confidence,
        risk=risk,
        requires_confirmation_probability=confirmation_probability,
        needs_reasoning_probability=reasoning_probability,
    )


def test_replayable_skips_baseline_errors_and_missing_signals() -> None:
    outcomes = [
        outcome(),
        outcome(case_id="llm-1", mode="llm"),
        outcome(case_id="err-1", error="boom"),
        outcome(case_id="old-1", confidence=None),
    ]

    kept = replayable(outcomes)

    assert [item.case_id for item in kept] == ["calc-001"]


def test_default_grid_is_non_trivial_and_deduplicated() -> None:
    grid = default_grid()

    assert len(grid) > 100
    assert len(set(grid)) == len(grid)
    assert PolicyThresholds() in grid


def test_calibration_never_executes_a_risky_tool_without_confirmation(
    tmp_path: Path,
) -> None:
    """写工具即使被模型判成无害，也必须落在确认里——这是策略层的下限。"""
    outcomes = [
        outcome(
            case_id="write-1",
            action="write_file",
            allowed=("write_file",),
            requires_confirmation=True,
        )
    ]

    result = calibrate(outcomes, registry(tmp_path), grid=(PolicyThresholds(),))

    row = result.rows[0]
    assert row.confirmed == 1
    assert row.executed == 0
    assert row.confirmation_mismatches == 0


def test_calibration_counts_a_wrong_auto_execution(tmp_path: Path) -> None:
    outcomes = [
        outcome(
            case_id="calc-2",
            action="calculator",
            allowed=("send_mock_email",),
            confidence=0.99,
        )
    ]

    result = calibrate(outcomes, registry(tmp_path), grid=(PolicyThresholds(),))

    row = result.rows[0]
    assert row.executed_wrong == 1
    assert row.score < 0


def test_calibration_prefers_a_threshold_that_escalates_the_uncertain_case(
    tmp_path: Path,
) -> None:
    """置信度低于阈值时委托，比把错的动作自动执行掉更好。"""
    uncertain = outcome(
        case_id="calc-3",
        action="calculator",
        allowed=("send_mock_email",),
        confidence=0.55,
    )
    confident = outcome(case_id="calc-4", confidence=0.99)

    result = calibrate(
        [uncertain, confident],
        registry(tmp_path),
        grid=(
            PolicyThresholds(confidence=0.50),
            PolicyThresholds(confidence=0.75),
        ),
    )

    best = result.best
    assert best is not None
    assert best.executed_wrong == 0
    assert best.thresholds.confidence == 0.75


def test_rows_are_ordered_by_score(tmp_path: Path) -> None:
    outcomes = [
        outcome(
            case_id="calc-5",
            action="calculator",
            allowed=("send_mock_email",),
            confidence=0.60,
        )
    ]

    result = calibrate(
        outcomes,
        registry(tmp_path),
        grid=(
            PolicyThresholds(confidence=0.40),
            PolicyThresholds(confidence=0.80),
        ),
    )

    scores = [row.score for row in result.rows]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(row, CalibrationRow) for row in result.rows)


def test_a_report_round_trips_through_the_loader(tmp_path: Path) -> None:
    original = [outcome(), outcome(case_id="mail-1", action="send_mock_email")]
    report = EvalReport(
        run_id="run-1",
        mode="jev",
        created_at="2026-10-31T00:00:00+00:00",
        outcomes=tuple(original),
        metrics=summarize(original),
    )
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(report_to_dict(report), ensure_ascii=False), encoding="utf-8"
    )

    loaded = load_outcomes(path)

    assert [item.case_id for item in loaded] == ["calc-001", "mail-1"]
    assert loaded[0].confidence == 0.9
    assert loaded[0].allowed_actions == ("calculator",)


def _write_report(path: Path, outcomes: list[CaseOutcome]) -> None:
    report = EvalReport(
        run_id="run-2",
        mode="jev",
        created_at="2026-10-31T00:00:00+00:00",
        outcomes=tuple(outcomes),
        metrics=summarize(outcomes),
    )
    path.write_text(
        json.dumps(report_to_dict(report), ensure_ascii=False), encoding="utf-8"
    )


def test_loader_refuses_a_foreign_version(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"version": 99, "data": {"outcomes": []}}), encoding="utf-8")

    with pytest.raises(ValueError, match="版本"):
        load_outcomes(path)


def test_loader_refuses_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    payload: dict[str, Any] = report_to_dict(
        EvalReport(
            run_id="run-3",
            mode="jev",
            created_at="2026-10-31T00:00:00+00:00",
            outcomes=(outcome(),),
            metrics=summarize([outcome()]),
        )
    )
    payload["data"]["outcomes"][0]["surprise"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="未知字段"):
        load_outcomes(path)


def test_cli_calibrate_needs_no_credentials(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """校准只读已记录的信号，所以它不该要求任何 provider 凭证。"""
    for name in ("JEV_API_KEY", "LLM_API_KEY", "JEV_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "report.json"
    _write_report(path, [outcome(), outcome(case_id="write-1", action="write_file")])

    code = main(["--mode", "calibrate", "--from-report", str(path), "--top", "3"])
    captured = capsys.readouterr()

    assert code == EXIT_OK
    assert "推荐阈值" in captured.out
    assert "JEV_CONFIRMATION_THRESHOLD=" in captured.out


def test_cli_calibrate_requires_a_report() -> None:
    assert main(["--mode", "calibrate"]) == EXIT_CONFIGURATION


def test_cli_calibrate_reports_an_unusable_report(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("JEV_API_KEY", "LLM_API_KEY", "JEV_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "empty.json"
    _write_report(path, [outcome(mode="llm")])

    code = main(["--mode", "calibrate", "--from-report", str(path)])

    assert code == EXIT_CONFIGURATION
    assert "没有可重放的用例" in capsys.readouterr().err


def test_cli_calibrate_writes_a_json_result(
    tmp_path: Path, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("JEV_API_KEY", "LLM_API_KEY", "JEV_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    report = tmp_path / "report.json"
    out = tmp_path / "calibration.json"
    _write_report(report, [outcome()])

    code = main(
        ["--mode", "calibrate", "--from-report", str(report), "--json-out", str(out)]
    )
    capsys.readouterr()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == EXIT_OK
    assert payload["data"]["best"]["thresholds"]["confidence"]
    assert payload["data"]["case_count"] == 1


def test_equal_scores_prefer_the_stricter_thresholds(tmp_path: Path) -> None:
    """同分时不该「碰巧」选中网格里排在前面的那组（通常是最松的）。"""
    outcomes = [outcome(confidence=0.9)]

    result = calibrate(
        outcomes,
        registry(tmp_path),
        grid=(
            PolicyThresholds(confidence=0.50),
            PolicyThresholds(confidence=0.75),
        ),
    )

    best = result.best
    assert best is not None
    assert best.thresholds.confidence == 0.75


def test_equal_scores_tighten_the_confirmation_valves_instead_of_loosening(
    tmp_path: Path,
) -> None:
    """确认与风险阈值是「越低越严」，同分时不能反过来取高。

    取高等于把两个安全阀关掉——而数据只说明「这批用例上没差别」。
    """
    outcomes = [outcome(confidence=0.9)]

    result = calibrate(
        outcomes,
        registry(tmp_path),
        grid=(
            PolicyThresholds(confirmation=0.50, risk=1.5),
            PolicyThresholds(confirmation=0.90, risk=3.5),
        ),
    )

    best = result.best
    assert best is not None
    assert best.thresholds.confirmation == 0.50
    assert best.thresholds.risk == 1.5


def test_boundary_hitting_optimum_is_reported(tmp_path: Path) -> None:
    """最优落在网格边沿时必须提示，否则「网格内最好」会被读成「最优点」。"""
    outcomes = [outcome(confidence=0.9)]

    result = calibrate(
        outcomes,
        registry(tmp_path),
        grid=(
            PolicyThresholds(confidence=0.50),
            PolicyThresholds(confidence=0.60),
            PolicyThresholds(confidence=0.70),
        ),
    )

    assert "confidence" in result.at_boundary


def test_an_interior_optimum_is_not_flagged(tmp_path: Path) -> None:
    outcomes = [
        outcome(case_id="a", confidence=0.85),
        outcome(
            case_id="b",
            action="calculator",
            allowed=("send_mock_email",),
            confidence=0.55,
        ),
    ]

    # 0.50 会把错的动作执行掉，0.90 又会把对的动作也委托出去，
    # 因此最优落在中间的两个候选之间，而不是边沿。
    result = calibrate(
        outcomes,
        registry(tmp_path),
        grid=(
            PolicyThresholds(confidence=0.50),
            PolicyThresholds(confidence=0.60),
            PolicyThresholds(confidence=0.70),
            PolicyThresholds(confidence=0.90),
        ),
    )

    assert "confidence" not in result.at_boundary


def test_inert_dimensions_are_called_out(tmp_path: Path) -> None:
    """怎么调都不影响结果的维度，不该被当成有依据的建议。"""
    outcomes = [outcome(confidence=0.9)]

    result = calibrate(
        outcomes,
        registry(tmp_path),
        grid=(
            PolicyThresholds(confirmation=0.50),
            PolicyThresholds(confirmation=0.90),
        ),
    )

    # 只有一条读类用例，确认阈值怎么调都不会改变它的结局。
    assert "confirmation" in result.inert_dimensions
