from __future__ import annotations

from typing import Any

import httpx
import pytest

from evals.cases import EvalCase
from evals.llm_router import LLMRouter
from evals.registry import default_registry
from evals.runner import EvalRunner
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.clients.llm import LLMCompletion
from jev_router.router import Router
from tests.support import FakeJev, route_answers

MODEL = "test-model"
LLM_MODEL = "claude-sonnet-4-5"

ALL_CANDIDATES = (
    "calculator",
    "knowledge_search",
    "web_search",
    "write_file",
    "send_mock_email",
    "ask_user",
    "delegate_to_llm",
    "finish",
)


class StubCompleter:
    def __init__(self, action: str) -> None:
        self.action = action

    async def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int | None = ...
    ) -> LLMCompletion:
        return LLMCompletion(
            text=f'{{"action": "{self.action}", "reason": "because"}}',
            model=LLM_MODEL,
            input_tokens=300,
            output_tokens=11,
        )


def case(
    case_id: str = "case-1",
    *,
    goal: str = "what is 2 + 2?",
    expected: str = "calculator",
    allowed: tuple[str, ...] = ("calculator",),
    requires_confirmation: bool = False,
) -> EvalCase:
    return EvalCase(
        id=case_id,
        goal=goal,
        expected_action=expected,
        allowed_actions=list(allowed),
        requires_confirmation=requires_confirmation,
    )


def jev_router(fake: FakeJev) -> Router:
    return Router(
        JevClient(JevClientConfig(api_key="test-key"), fake.transport()),
        MODEL,
        default_registry("/tmp/jevrouter-eval-tests"),
    )


def runner(tmp_path: Any, cases: tuple[EvalCase, ...], fake: FakeJev, llm_action: str | None) -> EvalRunner:
    return EvalRunner(
        cases=cases,
        tools=default_registry(tmp_path),
        jev_router=jev_router(fake),
        llm_router=None if llm_action is None else LLMRouter(StubCompleter(llm_action), LLM_MODEL, default_registry(tmp_path)),
    )


def queue(fake: FakeJev, action: str, **signals: Any) -> None:
    fake.routes.append(route_answers(action, ALL_CANDIDATES, **signals))


@pytest.mark.asyncio
async def test_jev_mode_records_a_matching_case(tmp_path: Any) -> None:
    fake = FakeJev()
    queue(fake, "calculator")
    subject = runner(tmp_path, (case(),), fake, None)
    report = await subject.run("jev")

    assert report.mode == "jev"
    assert len(report.outcomes) == 1
    outcome = report.outcomes[0]
    assert outcome.mode == "jev"
    assert outcome.action == "calculator"
    assert outcome.matched_expected and outcome.matched_allowed and outcome.succeeded
    assert outcome.policy_outcome == "execute"
    assert outcome.escalated is False
    assert outcome.confirmation_requested is False
    assert (outcome.input_tokens, outcome.output_tokens) == (10, 5)
    assert outcome.error is None
    assert report.metrics.jev is not None
    assert report.metrics.jev.case_count == 1
    assert report.metrics.jev.expected_match_rate == 1.0
    assert report.metrics.llm is None
    assert report.metrics.agreement_rate is None
    assert report.run_id and report.created_at


@pytest.mark.asyncio
async def test_a_write_tool_confirms_even_when_the_router_calls_it_harmless(
    tmp_path: Any,
) -> None:
    """风险下限压过模型的自我评估。

    路由把这个写操作说成「几乎无副作用」，但工具自己声明了 ``write``；
    度量必须和真正执行时一样要求确认，否则评测会给出一个线上不成立的结论。
    """
    fake = FakeJev()
    queue(fake, "write_file", risk=1.0, requires_confirmation=0.1)
    subject = runner(
        tmp_path,
        (case(expected="write_file", allowed=("write_file",), requires_confirmation=True),),
        fake,
        None,
    )
    report = await subject.run("jev")

    outcome = report.outcomes[0]
    assert outcome.policy_outcome == "ask_confirmation"
    assert outcome.confirmation_requested is True
    assert outcome.tool_risk == "write"
    assert outcome.succeeded is True


@pytest.mark.asyncio
async def test_confirmation_mismatch_fails_the_case(tmp_path: Any) -> None:
    fake = FakeJev()
    # 用例声称不需要确认，但它落的写工具按规则必须确认，于是这一条的确认行为
    # 与期望不符，不能算成功。
    queue(fake, "write_file", risk=1.0, requires_confirmation=0.1)
    subject = runner(
        tmp_path,
        (
            case(
                expected="write_file",
                allowed=("write_file",),
                requires_confirmation=False,
            ),
        ),
        fake,
        None,
    )
    report = await subject.run("jev")

    outcome = report.outcomes[0]
    assert outcome.policy_outcome == "ask_confirmation"
    assert outcome.confirmation_requested is True
    assert outcome.matched_allowed is True
    assert outcome.succeeded is False
    assert report.metrics.jev is not None
    assert report.metrics.jev.success_count == 0


@pytest.mark.asyncio
async def test_confirmation_request_counts_as_escalation(tmp_path: Any) -> None:
    fake = FakeJev()
    queue(fake, "send_mock_email", requires_confirmation=0.9)
    subject = runner(
        tmp_path,
        (case(expected="send_mock_email", allowed=("send_mock_email",), requires_confirmation=True),),
        fake,
        None,
    )
    report = await subject.run("jev")

    outcome = report.outcomes[0]
    assert outcome.policy_outcome == "ask_confirmation"
    assert outcome.confirmation_requested is True
    assert outcome.escalated is True
    assert outcome.succeeded is True
    metrics = report.metrics.jev
    assert metrics is not None
    assert metrics.confirmation_requested_count == 1
    assert metrics.confirmation_match_count == 1


@pytest.mark.asyncio
async def test_router_failure_becomes_an_error_outcome(tmp_path: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "provider down"})

    subject = EvalRunner(
        cases=(case(),),
        tools=default_registry(tmp_path),
        jev_router=Router(
            JevClient(JevClientConfig(api_key="k"), httpx.MockTransport(handler)),
            MODEL,
            default_registry(tmp_path),
        ),
    )
    report = await subject.run("jev")

    outcome = report.outcomes[0]
    assert outcome.action is None
    assert outcome.error is not None and "http" in outcome.error
    assert outcome.succeeded is False
    assert report.metrics.jev is not None
    assert report.metrics.jev.error_count == 1


@pytest.mark.asyncio
async def test_compare_mode_runs_both_routers_and_measures_agreement(tmp_path: Any) -> None:
    fake = FakeJev()
    queue(fake, "calculator")
    queue(fake, "web_search")
    cases = (
        case("case-1", goal="what is 2 + 2?"),
        case("case-2", goal="what is the weather?", expected="web_search", allowed=("web_search",)),
    )
    subject = EvalRunner(
        cases=cases,
        tools=default_registry(tmp_path),
        jev_router=jev_router(fake),
        llm_router=LLMRouter(StubCompleter("web_search"), LLM_MODEL, default_registry(tmp_path)),
    )
    report = await subject.run("compare")

    assert len(report.outcomes) == 4
    assert {outcome.mode for outcome in report.outcomes} == {"jev", "llm"}
    assert report.metrics.jev is not None and report.metrics.jev.case_count == 2
    assert report.metrics.llm is not None and report.metrics.llm.case_count == 2
    # 基线两次都回答了 web_search，因此只在 case-2 上一致。
    assert report.metrics.compared_count == 2
    assert report.metrics.agreement_count == 1
    assert report.metrics.agreement_rate == 0.5
    assert report.metrics.disagreement_case_ids == ("case-1",)
    # 基线没有策略结果，因此这些指标保持缺省。
    assert report.metrics.llm is not None
    assert report.metrics.llm.escalation_count is None
    assert report.metrics.llm.confirmation_requested_count is None


@pytest.mark.asyncio
async def test_compare_mode_skips_agreement_when_a_router_errored(tmp_path: Any) -> None:
    fake = FakeJev()
    # 没有排队的路由应答，因此 Jev 一侧失败；基线仍会作答。
    subject = runner(tmp_path, (case(),), fake, "calculator")
    report = await subject.run("compare")

    jev_outcome = next(outcome for outcome in report.outcomes if outcome.mode == "jev")
    llm_outcome = next(outcome for outcome in report.outcomes if outcome.mode == "llm")
    assert jev_outcome.error is not None
    assert llm_outcome.action == "calculator"
    assert report.metrics.compared_count == 0
    assert report.metrics.agreement_rate is None


@pytest.mark.asyncio
async def test_mode_without_its_router_is_refused(tmp_path: Any) -> None:
    subject = EvalRunner(cases=(case(),), tools=default_registry(tmp_path))
    with pytest.raises(ValueError, match="Jev router"):
        await subject.run("jev")
    with pytest.raises(ValueError, match="baseline router"):
        await subject.run("llm")


def test_no_cases_is_refused(tmp_path: Any) -> None:
    with pytest.raises(ValueError, match="at least one case"):
        EvalRunner(cases=(), tools=default_registry(tmp_path))


@pytest.mark.asyncio
async def test_explicit_run_id_is_kept(tmp_path: Any) -> None:
    fake = FakeJev()
    queue(fake, "calculator")
    report = await runner(tmp_path, (case(),), fake, None).run("jev", run_id="fixed-run")
    assert report.run_id == "fixed-run"
