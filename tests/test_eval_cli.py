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
    monkeypatch.setattr(cli, "_llm_router", lambda model, max_tokens=None, timeout=None: FakeLLMRouter())


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


def test_the_api_posts_the_report_envelope(monkeypatch: Any, tmp_path: Any) -> None:
    import httpx

    from evals.report import REPORT_VERSION

    patch_routers(monkeypatch)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"run_id": "run-1", "case_count": 3})

    real_client = httpx.Client
    monkeypatch.setattr(
        cli.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    code = cli.main(["--mode", "compare", "--limit", "3", "--api", "http://api.test/"])

    assert code == cli.EXIT_OK
    assert captured["path"] == "/evals"
    body = captured["body"]
    assert "version" not in body, "the API takes the envelope's data, not the envelope"
    assert body["mode"] == "compare"
    assert len(body["outcomes"]) == 6
    assert body["metrics"]["jev"]["case_count"] == 3
    assert REPORT_VERSION == 1


def test_an_unreachable_api_fails_the_delivery(monkeypatch: Any) -> None:
    import httpx

    patch_routers(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    real_client = httpx.Client
    monkeypatch.setattr(
        cli.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    code = cli.main(["--mode", "jev", "--limit", "1", "--api", "http://api.test"])

    assert code == cli.EXIT_DELIVERY


def test_a_refused_report_reports_the_api_message(monkeypatch: Any, capsys: Any) -> None:
    import httpx

    patch_routers(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"loc": ["body", "mode"], "msg": "unknown"}]})

    real_client = httpx.Client
    monkeypatch.setattr(
        cli.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    code = cli.main(["--mode", "jev", "--limit", "1", "--api", "http://api.test"])

    assert code == cli.EXIT_DELIVERY
    assert "body.mode: unknown" in capsys.readouterr().err


def test_the_llm_budget_and_timeout_flags_reach_the_client(monkeypatch: Any) -> None:


    captured: dict[str, Any] = {}

    def fake_router(model: str, max_tokens: int | None, timeout: float | None) -> Any:
        captured["max_tokens"] = max_tokens
        captured["timeout"] = timeout
        return FakeLLMRouter()

    monkeypatch.setattr(cli, "_llm_router", fake_router)
    monkeypatch.setattr(cli, "_jev_router", lambda model: FakeJevRouter())
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "step-5-preview")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("LLM_API_STYLE", "chat_completions")

    code = cli.main(
        ["--mode", "compare", "--limit", "1", "--llm-max-tokens", "8192", "--llm-timeout", "90"]
    )

    assert code == cli.EXIT_OK
    assert captured == {"max_tokens": 8192, "timeout": 90.0}


def test_the_llm_flags_default_to_the_environment(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_router(model: str, max_tokens: int | None, timeout: float | None) -> Any:
        captured["max_tokens"] = max_tokens
        captured["timeout"] = timeout
        return FakeLLMRouter()

    monkeypatch.setattr(cli, "_llm_router", fake_router)
    monkeypatch.setattr(cli, "_jev_router", lambda model: FakeJevRouter())
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)

    code = cli.main(["--mode", "compare", "--limit", "1"])

    assert code == cli.EXIT_OK
    assert captured == {"max_tokens": None, "timeout": None}
