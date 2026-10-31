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

from evals.calibrate import CalibrationRow, calibrate, load_outcomes
from evals.cases import CaseFileError, load_cases
from evals.llm_router import LLMRouter
from evals.metrics import TokenStats
from evals.registry import default_registry
from evals.report import report_to_dict
from evals.runner import EvalReport, EvalRunner
from jev_router.clients.jev import JevClient, JevClientConfig, JevClientError
from jev_router.clients.llm import LLMClient, LLMClientConfig, LLMClientError
from jev_router.policy import PolicyThresholds
from jev_router.router import Router

EXIT_OK = 0
EXIT_CASE_ERRORS = 1
EXIT_CONFIGURATION = 2
EXIT_DELIVERY = 3

API_TIMEOUT_SECONDS = 30.0

DEFAULT_TOP_ROWS = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description=(
            "把固定的路由用例集重放进 Jev、LLM 基线或两者，并在已记录的信号上校准策略阈值。"
        ),
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="版本化用例文件的路径（默认使用仓库内的 evals/cases.json）",
    )
    parser.add_argument(
        "--mode",
        choices=("jev", "llm", "compare", "calibrate"),
        default="compare",
        help=(
            "要跑哪些路由层（默认 compare）。calibrate 不调用任何 provider，"
            "它只重放 --from-report 里已经记录下来的信号"
        ),
    )
    parser.add_argument("--jev-model", default=None, help="Jev 模型 id（默认取 $JEV_MODEL）")
    parser.add_argument("--llm-model", default=None, help="LLM 模型 id（默认取 $LLM_MODEL）")
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=None,
        help=(
            "基线的 completion 预算（默认取 $LLM_MAX_TOKENS，否则 1024）。"
            "推理模型会先把它消耗在思考上，跑这类模型时要调大"
        ),
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=None,
        help="基线单次请求的超时秒数（默认取 $LLM_TIMEOUT_SECONDS，否则 30）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只跑文件顺序里的前 N 条用例（默认全部）",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="把版本化报告写到这个路径，而不只是打印摘要",
    )
    parser.add_argument(
        "--api",
        default=None,
        help="把跑完的报告投递给这个 API 地址（例如 http://127.0.0.1:8000）",
    )
    parser.add_argument(
        "--from-report",
        default=None,
        help="calibrate 模式的输入：一份先前用 --json-out 写出的报告",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_ROWS,
        help=f"calibrate 模式打印前 N 组阈值（默认 {DEFAULT_TOP_ROWS}）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "calibrate":
        return _run_calibration(args)

    try:
        cases = load_cases(args.cases) if args.cases else load_cases()
    except CaseFileError as exc:
        print(f"用例文件有问题：{exc}", file=sys.stderr)
        return EXIT_CONFIGURATION
    if args.limit is not None:
        if args.limit < 1:
            print("--limit 必须是正整数", file=sys.stderr)
            return EXIT_CONFIGURATION
        cases = cases[: args.limit]

    try:
        jev = _jev_router(args.jev_model) if args.mode in ("jev", "compare") else None
        llm = (
            _llm_router(args.llm_model, args.llm_max_tokens, args.llm_timeout)
            if args.mode in ("llm", "compare")
            else None
        )
    except (JevClientError, LLMClientError, ValueError) as exc:
        print(f"配置有问题：{exc}", file=sys.stderr)
        return EXIT_CONFIGURATION

    runner = EvalRunner(
        cases=cases,
        tools=default_registry(_workspace()),
        jev_router=jev,
        llm_router=llm,
        thresholds=_thresholds_from_env(),
    )
    report = asyncio.run(runner.run(args.mode))
    _print_summary(report)

    if args.json_out:
        payload = report_to_dict(report)
        destination = Path(args.json_out)
        if destination.parent and not destination.parent.exists():
            print(f"输出目录不存在：{destination.parent}", file=sys.stderr)
            return EXIT_CONFIGURATION
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"报告已写入 {destination}")

    errors = sum(1 for outcome in report.outcomes if outcome.error is not None)
    if errors:
        print(f"{errors} 条用例出错", file=sys.stderr)

    if args.api:
        delivery = _post_report(args.api, report)
        if delivery is not None:
            return delivery
    return EXIT_CASE_ERRORS if errors else EXIT_OK


def _run_calibration(args: argparse.Namespace) -> int:
    if not args.from_report:
        print("calibrate 模式需要 --from-report 指定一份已有报告", file=sys.stderr)
        return EXIT_CONFIGURATION
    try:
        outcomes = load_outcomes(args.from_report)
    except (TypeError, ValueError) as exc:
        print(f"报告无法读取：{exc}", file=sys.stderr)
        return EXIT_CONFIGURATION
    if args.top < 1:
        print("--top 必须是正整数", file=sys.stderr)
        return EXIT_CONFIGURATION

    result = calibrate(outcomes, default_registry(_workspace()))
    if result.case_count == 0:
        print(
            "这份报告里没有可重放的用例：需要带 confidence / risk / "
            "requires_confirmation_probability / needs_reasoning_probability 的记录",
            file=sys.stderr,
        )
        return EXIT_CONFIGURATION

    print(
        f"在 {result.case_count} 条 Jev 用例上回放策略；"
        f"跳过 {result.skipped_count} 条无法重放的记录"
    )
    header = (
        f"{'confirmation':>12} {'risk':>5} {'reasoning':>9} {'confidence':>10}  "
        f"{'执行':>6} {'确认':>6} {'升级':>6} {'错执行':>6} {'错确认':>6} {'确认失配':>8} {'得分':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in result.rows[: args.top]:
        t = row.thresholds
        print(
            f"{t.confirmation:>12.2f} {t.risk:>5.1f} {t.reasoning:>9.2f} {t.confidence:>10.2f}  "
            f"{row.executed:>6} {row.confirmed:>6} {row.delegated:>6} "
            f"{row.executed_wrong:>6} {row.confirmed_wrong:>6} {row.confirmation_mismatches:>8} "
            f"{row.score:>7.1f}"
        )

    best = result.best
    if best is not None:
        t = best.thresholds
        print()
        print("推荐阈值（复制到 .env 即生效）：")
        print(f"  JEV_CONFIRMATION_THRESHOLD={t.confirmation:.2f}")
        print(f"  JEV_RISK_THRESHOLD={t.risk:.1f}")
        print(f"  JEV_REASONING_THRESHOLD={t.reasoning:.2f}")
        print(f"  JEV_ROUTE_CONFIDENCE_THRESHOLD={t.confidence:.2f}")
        print(
            f"  该组合：自动执行 {best.executed} 条、请人确认 {best.confirmed} 条、"
            f"委托 {best.delegated} 条；"
            f"错误的动作被自动执行 {best.executed_wrong} 次"
        )
        if result.inert_dimensions:
            print(
                f"  · 这些维度在本批用例上无论怎么调都不改变结果："
                f"{', '.join(result.inert_dimensions)}。它们的推荐值只是同分任取，"
                "没有证据支持改动，建议保持现状。"
            )
        if result.at_boundary:
            print(
                f"  ⚠ 这些维度取到了搜索范围的边沿：{', '.join(result.at_boundary)}。"
                "说明真实最优可能在范围之外，这个结果只能读作「当前网格内最好」。"
            )

    if args.json_out:
        destination = Path(args.json_out)
        if destination.parent and not destination.parent.exists():
            print(f"输出目录不存在：{destination.parent}", file=sys.stderr)
            return EXIT_CONFIGURATION
        payload = {
            "version": 1,
            "data": {
                "case_count": result.case_count,
                "skipped_count": result.skipped_count,
                "best": None if best is None else _row_to_dict(best),
                "at_boundary": list(result.at_boundary),
                "inert_dimensions": list(result.inert_dimensions),
                "rows": [_row_to_dict(row) for row in result.rows[: args.top]],
            },
        }
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"校准结果已写入 {destination}")
    return EXIT_OK


def _row_to_dict(row: CalibrationRow) -> dict[str, object]:
    return {
        "thresholds": row.thresholds.as_dict(),
        "executed": row.executed,
        "confirmed": row.confirmed,
        "delegated": row.delegated,
        "executed_correct": row.executed_correct,
        "executed_wrong": row.executed_wrong,
        "confirmed_wrong": row.confirmed_wrong,
        "confirmation_mismatches": row.confirmation_mismatches,
        "matched_allowed": row.matched_allowed,
        "score": row.score,
    }


def _thresholds_from_env() -> PolicyThresholds:
    return PolicyThresholds(
        confirmation=_env_float("JEV_CONFIRMATION_THRESHOLD", 0.75),
        risk=_env_float("JEV_RISK_THRESHOLD", 2.5),
        reasoning=_env_float("JEV_REASONING_THRESHOLD", 0.70),
        confidence=_env_float("JEV_ROUTE_CONFIDENCE_THRESHOLD", 0.75),
    )



def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc


def _post_report(api: str, report: EvalReport) -> int | None:
    """把报告 POST 给运行中的 API。``None`` 表示对方接受了。

    请求体就是报告信封里的 ``data``，正好是 ``POST /evals`` 校验的那个形状，
    所以被拒绝只能说明报告与 API 对不上——直接回传 API 自己的说法，不猜。
    """
    body = report_to_dict(report)["data"]
    try:
        with httpx.Client(timeout=API_TIMEOUT_SECONDS) as client:
            response = client.post(api.rstrip("/") + "/evals", json=body)
    except httpx.HTTPError as exc:
        print(f"连不上 API：{exc}", file=sys.stderr)
        return EXIT_DELIVERY
    if response.is_error:
        print(
            f"API 拒绝了这份报告：{response.status_code} {_problem(response)}",
            file=sys.stderr,
        )
        return EXIT_DELIVERY
    print(f"报告已记录为 {response.json().get('run_id', report.run_id)}")
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
        raise ValueError("需要指定 Jev 模型（--jev-model 或 $JEV_MODEL）")
    return Router(JevClient(config), resolved, default_registry(_workspace()))


def _llm_router(model: str | None, max_tokens: int | None, timeout: float | None) -> LLMRouter:
    config = LLMClientConfig.from_env()
    resolved = model or _env("LLM_MODEL")
    if not resolved:
        raise ValueError("需要指定 LLM 模型（--llm-model 或 $LLM_MODEL）")
    if max_tokens is not None or timeout is not None:
        # 基线是一件测量仪器：推理模型需要一份委托与参数合成会嫌浪费的预算，
        # 所以评测有自己的旋钮，而不是让整个环境跟着改。
        config = LLMClientConfig(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds if timeout is None else timeout,
            max_tokens=config.max_tokens if max_tokens is None else max_tokens,
            api_version=config.api_version,
            api_style=config.api_style,
        )
    return LLMRouter(LLMClient(config), resolved, default_registry(_workspace()))


def _workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="jevrouter-eval-"))


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _print_summary(report: EvalReport) -> None:
    print(f"运行 {report.run_id}（{report.mode}）于 {report.created_at}")
    for metrics in (report.metrics.jev, report.metrics.llm):
        if metrics is None:
            continue
        print(
            f"  {metrics.mode:<4} 用例 {metrics.case_count}  "
            f"期望命中 {_ratio(metrics.expected_match_count, metrics.case_count)}  "
            f"允许集命中 {_ratio(metrics.allowed_match_count, metrics.case_count)}  "
            f"成功 {_ratio(metrics.success_count, metrics.case_count)}  "
            f"升级 {_ratio(metrics.escalation_count, metrics.case_count) if metrics.escalation_count is not None else '—'}  "
            f"确认 {_ratio(metrics.confirmation_requested_count, metrics.case_count) if metrics.confirmation_requested_count is not None else '—'}  "
            f"错误 {metrics.error_count}"
        )
        latency = metrics.latency
        print(
            f"       延迟 均值 {latency.mean_ms:.0f} ms  p50 {latency.p50_ms} ms  "
            f"p95 {latency.p95_ms} ms  最大 {latency.max_ms} ms  "
            f"token 输入 {_tokens(metrics.input_tokens)}  输出 {_tokens(metrics.output_tokens)}"
        )
    if report.metrics.agreement_rate is not None:
        print(
            f"  一致率 {report.metrics.agreement_count}/{report.metrics.compared_count} "
            f"({report.metrics.agreement_rate * 100:.1f}%)"
        )
        if report.metrics.disagreement_case_ids:
            print(f"  分歧用例：{', '.join(report.metrics.disagreement_case_ids)}")


def _ratio(count: int | None, total: int) -> str:
    if count is None:
        return "—"
    return f"{count}/{total} ({(count / total * 100) if total else 0:.1f}%)"


def _tokens(tokens: TokenStats | None) -> str:
    if tokens is None:
        return "—"
    return f"{tokens.total}（均值 {tokens.mean:.1f}）"
