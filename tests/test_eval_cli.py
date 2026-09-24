from __future__ import annotations

import json
from typing import Any

from evals import cli


class FakeJevRouter:
    """Routes every case to `calculator` without touching a provider."""

    async def route(self, state: Any) -> Any:
        from jev_router.router import RouteDecision

        return RouteDecision(
            action="calculator",
            confidence=0.9,
            risk=1.0,
            risk_confidence=0.8,
            requires_confirmation=0.1,
            needs_reasoning=0.1,
            model="fake-jev",
            input_tokens=10,
            output_tokens=5,
        )


class FakeLLMRouter:
    async def route(self, state: Any) -> Any:
        from evals.llm_router import LLMRouteDecision

        return LLMRouteDecision(
            action="calculator",
            reason="arithmetic",
            model="fake-llm",
            latency_ms=42,
            input_tokens=300,
            output_tokens=11,
        )


def patch_routers(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli, "_jev_router", lambda model: FakeJevRouter())
    monkeypatch.setattr(cli, "_llm_router", lambda model: FakeLLMRouter())


def test_missing_credentials_are_a_configuration_error(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.delenv("JEV_MODEL", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    code = cli.main(["--mode", "jev"])
    assert code == cli.EXIT_CONFIGURATION
    assert "configuration error" in capsys.readouterr().err


def test_missing_llm_credentials_are_a_configuration_error(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    code = cli.main(["--mode", "llm"])
    assert code == cli.EXIT_CONFIGURATION
    assert "configuration error" in capsys.readouterr().err


def test_non_positive_limit_is_refused() -> None:
    assert cli.main(["--limit", "0"]) == cli.EXIT_CONFIGURATION


def test_missing_case_file_is_a_configuration_error(capsys: Any) -> None:
    assert cli.main(["--cases", "/nonexistent/cases.json"]) == cli.EXIT_CONFIGURATION
    assert "case file error" in capsys.readouterr().err


def test_clean_run_writes_a_versioned_report(
    monkeypatch: Any, tmp_path: Any, capsys: Any
) -> None:
    patch_routers(monkeypatch)
    destination = tmp_path / "report.json"
    code = cli.main(
        ["--mode", "compare", "--limit", "3", "--json-out", str(destination)]
    )
    assert code == cli.EXIT_OK
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    data = payload["data"]
    assert data["mode"] == "compare"
    assert len(data["outcomes"]) == 6  # three cases, two routers
    assert data["metrics"]["agreement_count"] == 3
    assert data["metrics"]["jev"]["case_count"] == 3
    assert data["metrics"]["jev"]["expected_match_rate"] == 1.0
    summary = capsys.readouterr().out
    assert "agreement 3/3" in summary
    assert "report written to" in summary


def test_unwritable_output_directory_is_refused(monkeypatch: Any) -> None:
    patch_routers(monkeypatch)
    code = cli.main(["--mode", "jev", "--limit", "1", "--json-out", "/nonexistent/dir/report.json"])
    assert code == cli.EXIT_CONFIGURATION


def test_a_run_with_errors_exits_non_zero(monkeypatch: Any, capsys: Any) -> None:
    class BrokenRouter:
        async def route(self, state: Any) -> Any:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(cli, "_jev_router", lambda model: BrokenRouter())
    code = cli.main(["--mode", "jev", "--limit", "2"])
    assert code == cli.EXIT_CASE_ERRORS
    assert "case(s) errored" in capsys.readouterr().err


def test_real_routers_are_constructible_without_credentials(monkeypatch: Any) -> None:
    """The factory helpers are exercised by the CLI; here they must fail closed."""
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    from jev_router.clients.jev import JevClientError

    try:
        cli._jev_router("some-model")
    except JevClientError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("a missing credential must fail closed")
