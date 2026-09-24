from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import httpx

from evals.cases import CaseFileError, load_cases
from evals.llm_router import LLMRouter
from evals.metrics import TokenStats
from evals.registry import default_registry
from evals.report import report_to_dict
from evals.runner import EvalReport, EvalRunner
from jev_router.clients.jev import JevClient, JevClientConfig, JevClientError
from jev_router.clients.llm import LLMClient, LLMClientConfig, LLMClientError
from jev_router.router import Router

EXIT_OK = 0
EXIT_CASE_ERRORS = 1
EXIT_CONFIGURATION = 2
EXIT_DELIVERY = 3

API_TIMEOUT_SECONDS = 30.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="Replay the fixed routing case set through Jev, an LLM baseline, or both.",
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="path to the versioned case file (default: the committed evals/cases.json)",
    )
    parser.add_argument(
        "--mode",
        choices=("jev", "llm", "compare"),
        default="compare",
        help="which routers to run (default: compare)",
    )
    parser.add_argument("--jev-model", default=None, help="Jev model id (default: $JEV_MODEL)")
    parser.add_argument("--llm-model", default=None, help="LLM model id (default: $LLM_MODEL)")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="run only the first N cases in file order (default: all)",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="write the versioned report to this path instead of only printing a summary",
    )
    parser.add_argument(
        "--api",
        default=None,
        help="post the finished report to this API base URL (e.g. http://127.0.0.1:8000)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_cases(args.cases) if args.cases else load_cases()
    except CaseFileError as exc:
        print(f"case file error: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION
    if args.limit is not None:
        if args.limit < 1:
            print("limit must be positive", file=sys.stderr)
            return EXIT_CONFIGURATION
        cases = cases[: args.limit]

    try:
        jev = _jev_router(args.jev_model) if args.mode in ("jev", "compare") else None
        llm = _llm_router(args.llm_model) if args.mode in ("llm", "compare") else None
    except (JevClientError, LLMClientError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION

    runner = EvalRunner(cases=cases, tools=default_registry(_workspace()), jev_router=jev, llm_router=llm)
    report = asyncio.run(runner.run(args.mode))
    _print_summary(report)

    if args.json_out:
        payload = report_to_dict(report)
        destination = Path(args.json_out)
        if destination.parent and not destination.parent.exists():
            print(f"output directory does not exist: {destination.parent}", file=sys.stderr)
            return EXIT_CONFIGURATION
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"report written to {destination}")

    errors = sum(1 for outcome in report.outcomes if outcome.error is not None)
    if errors:
        print(f"{errors} case(s) errored", file=sys.stderr)

    if args.api:
        delivery = _post_report(args.api, report)
        if delivery is not None:
            return delivery
    return EXIT_CASE_ERRORS if errors else EXIT_OK


def _post_report(api: str, report: EvalReport) -> int | None:
    """POST the report to a running API. ``None`` means it was accepted.

    The body is the report envelope's ``data``, which is exactly what
    ``POST /evals`` validates, so a refusal means the report and the API disagree
    — reported with the API's own message rather than guessed at.
    """
    body = report_to_dict(report)["data"]
    try:
        with httpx.Client(timeout=API_TIMEOUT_SECONDS) as client:
            response = client.post(api.rstrip("/") + "/evals", json=body)
    except httpx.HTTPError as exc:
        print(f"the API could not be reached: {exc}", file=sys.stderr)
        return EXIT_DELIVERY
    if response.is_error:
        print(
            f"the API refused the report: {response.status_code} {_problem(response)}",
            file=sys.stderr,
        )
        return EXIT_DELIVERY
    print(f"report recorded as {response.json().get('run_id', report.run_id)}")
    return None


def _problem(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return "; ".join(
            f"{'.'.join(str(part) for part in entry.get('loc', []))}: {entry.get('msg')}"
            for entry in detail
            if isinstance(entry, dict)
        )
    return response.text[:200]


def _jev_router(model: str | None) -> Router:
    config = JevClientConfig.from_env()
    resolved = model or _env("JEV_MODEL")
    if not resolved:
        raise ValueError("a Jev model is required (--jev-model or $JEV_MODEL)")
    return Router(JevClient(config), resolved, default_registry(_workspace()))


def _llm_router(model: str | None) -> LLMRouter:
    config = LLMClientConfig.from_env()
    resolved = model or _env("LLM_MODEL")
    if not resolved:
        raise ValueError("an LLM model is required (--llm-model or $LLM_MODEL)")
    return LLMRouter(LLMClient(config), resolved, default_registry(_workspace()))


def _workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="jevrouter-eval-"))


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _print_summary(report: EvalReport) -> None:
    print(f"run {report.run_id} ({report.mode}) at {report.created_at}")
    for metrics in (report.metrics.jev, report.metrics.llm):
        if metrics is None:
            continue
        print(
            f"  {metrics.mode:<4} cases {metrics.case_count}  "
            f"expected {_ratio(metrics.expected_match_count, metrics.case_count)}  "
            f"allowed {_ratio(metrics.allowed_match_count, metrics.case_count)}  "
            f"success {_ratio(metrics.success_count, metrics.case_count)}  "
            f"escalated {_ratio(metrics.escalation_count, metrics.case_count) if metrics.escalation_count is not None else '—'}  "
            f"confirm {_ratio(metrics.confirmation_requested_count, metrics.case_count) if metrics.confirmation_requested_count is not None else '—'}  "
            f"errors {metrics.error_count}"
        )
        latency = metrics.latency
        print(
            f"       latency mean {latency.mean_ms:.0f} ms  p50 {latency.p50_ms} ms  "
            f"p95 {latency.p95_ms} ms  max {latency.max_ms} ms  "
            f"tokens in {_tokens(metrics.input_tokens)}  out {_tokens(metrics.output_tokens)}"
        )
    if report.metrics.agreement_rate is not None:
        print(
            f"  agreement {report.metrics.agreement_count}/{report.metrics.compared_count} "
            f"({report.metrics.agreement_rate * 100:.1f}%)"
        )
        if report.metrics.disagreement_case_ids:
            print(f"  disagreements: {', '.join(report.metrics.disagreement_case_ids)}")


def _ratio(count: int | None, total: int) -> str:
    if count is None:
        return "—"
    return f"{count}/{total} ({(count / total * 100) if total else 0:.1f}%)"


def _tokens(tokens: TokenStats | None) -> str:
    if tokens is None:
        return "—"
    return f"{tokens.total} (mean {tokens.mean:.1f})"
