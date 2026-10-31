from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from apps.api.config import Settings
from apps.api.llm import LLMArgumentResolver, LLMDelegate
from apps.api.schemas import AWAITING_CONFIRMATION, AWAITING_INPUT, RUNNING
from apps.api.storage import TraceStore
from jev_router.clients.jev import JevClient
from jev_router.clients.llm import LLMClient
from jev_router.runner import Runner, RunResult, StepTrace
from jev_router.state import TaskState
from jev_router.tools.registry import ToolRegistry

# 委托提示词保持英文：它是发给模型的协议指令，不是项目界面的一部分，
# 改动它会连带改变模型行为，让已有的评测结果失去可比性。
_DELEGATE_SYSTEM = (
    "You are the reasoning delegate of an agent. The router decided that this "
    "step needs deeper reasoning than a typed decision can provide. Produce the "
    "answer or the concrete content that advances the task, as plain text."
)

_RESULT_LIMIT = 500


class UnknownTaskError(KeyError):
    """任务 id 在本进程内不存在时抛出。"""


class ConfirmationConflict(ValueError):
    """确认请求与待确认的事项对不上（摘要不符、已过期或根本没有在等）。"""


def confirmation_digest(task_id: str, action: str, arguments: dict[str, Any]) -> str:
    """把「确认的是哪件事」压成一个短摘要。

    摘要绑定任务、动作与参数三者，因此人工看到的那份参数一旦变化，旧的批准
    就无法被复用——docs/security.md 要求的正是这一点。
    """
    payload = json.dumps(
        {"task": task_id, "action": action, "arguments": arguments},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class PendingConfirmation:
    action: str
    arguments: dict[str, Any]
    step: int
    digest: str
    expires_at: datetime



@dataclass
class PendingInput:
    question: str
    step: int


@dataclass
class RunHandle:
    task_id: str
    goal: str
    status: str
    step: int = 0
    diagnostic: str | None = None
    pending_confirmation: PendingConfirmation | None = None
    pending_input: PendingInput | None = None


class _RunHandlers:
    """把一次运行里的阻塞式请求绑定到它的任务 id。

    ``ConfirmationHandler`` 会收到任务 id，而 ``UserInputHandler`` 不会，
    所以两者都经过这层适配器，由它补上自己已知的 id。
    """

    def __init__(self, service: TaskService, task_id: str) -> None:
        self._service = service
        self._task_id = task_id

    async def confirm(
        self,
        task_id: str,
        action: str,
        arguments: Any,
        state: TaskState,
    ) -> bool:
        return await self._service._await_confirmation(
            self._task_id, action, arguments, state
        )

    async def request_input(self, question: str, state: TaskState) -> str | None:
        return await self._service._await_input(self._task_id, question, state)


class TaskService:
    """在后台驱动运行，并把它们暴露给 HTTP 处理器。

    一次运行的生命周期长于发起它的那个请求，因此确认与用户输入由后续请求
    通过 future 解决，而不是靠阻塞等待。执行循环本身不用改：它只是 await 一个
    「恰好要等真人」的处理器。
    """

    def __init__(
        self,
        *,
        store: TraceStore,
        settings: Settings,
        tools: ToolRegistry,
        resolver: Any,
        client: JevClient | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._tools = tools
        self._client = client or JevClient(settings.jev)
        # 显式注入的 resolver 优先：它是调用方自己的接缝（测试用的就是它），
        # 而 LLM 版是「什么都没配」时的兜底。
        self._delegate, llm_resolver = self._build_llm_collaborators(llm_client)

        self._resolver = resolver if resolver is not None else llm_resolver
        self._handles: dict[str, RunHandle] = {}
        self._confirmations: dict[str, asyncio.Future[bool]] = {}
        self._inputs: dict[str, asyncio.Future[str | None]] = {}
        self._runs: dict[str, asyncio.Task[None]] = {}

    def _build_llm_collaborators(
        self, llm_client: LLMClient | None
    ) -> tuple[LLMDelegate | None, LLMArgumentResolver | None]:
        """用同一份 LLM 配置装配委托处理器与参数合成器。

        没有 LLM 配置时，服务保持第七阶段交付时的 fail closed 形态：委托请求会
        直接终止运行，工具参数解析成空，由工具自己的 schema 拒绝它。两者共用一份
        配置，因为「会推理但不会给参数」的 agent 没有用。
        """

        if self._settings.llm is None or self._settings.llm_model is None:
            return None, None
        client = llm_client or LLMClient(self._settings.llm)
        model = self._settings.llm_model
        return LLMDelegate(client, model), LLMArgumentResolver(client, model, self._tools)

    def submit(
        self,
        goal: str,
        *,
        context: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> RunHandle:
        identifier = task_id or uuid4().hex
        if identifier in self._handles:
            raise ValueError(f"任务 {identifier!r} 已经存在")
        handle = RunHandle(task_id=identifier, goal=goal, status=RUNNING)
        self._handles[identifier] = handle
        runner = Runner(
            client=self._client,
            model=self._settings.model,
            tools=self._tools,
            budget=self._settings.budget(),
            completion_threshold=self._settings.completion_threshold,
            thresholds=self._settings.policy_thresholds(),
            resolver=self._resolver,
            confirmation=_RunHandlers(self, identifier),
            user_input=_RunHandlers(self, identifier),
            delegate=self._delegate,
            trace_sink=self._store.sink(),
        )

        self._runs[identifier] = asyncio.get_running_loop().create_task(
            self._drive(identifier, runner, goal, context)
        )
        return handle

    def get(self, task_id: str) -> RunHandle:
        try:
            return self._handles[task_id]
        except KeyError as exc:
            raise UnknownTaskError(task_id) from exc

    def list(self, limit: int = 50) -> tuple[RunHandle, ...]:
        if limit < 1:
            raise ValueError("limit 必须是正数")
        return tuple(reversed(list(self._handles.values())))[:limit]

    def traces(self, task_id: str) -> tuple[StepTrace, ...]:
        self.get(task_id)
        return self._store.load_traces(task_id)

    def confirm(self, task_id: str, approved: bool, digest: str) -> None:
        """回应一次待确认。摘要不符即拒绝，批准不能被嫁接到另一份参数上。"""
        self.get(task_id)
        pending = self._handles[task_id].pending_confirmation
        future = self._confirmations.get(task_id)
        if pending is None or future is None or future.done():
            raise ConfirmationConflict("该任务当前没有在等待确认")
        if digest != pending.digest:
            raise ConfirmationConflict("确认摘要与待确认的事项不一致")
        future.set_result(approved)

    def provide_input(self, task_id: str, answer: str) -> None:
        self.get(task_id)
        future = self._inputs.get(task_id)
        if future is None or future.done():
            raise UnknownTaskError(f"任务 {task_id!r} 没有在等待用户输入")
        future.set_result(answer)


    async def shutdown(self) -> None:
        for task_id, run in list(self._runs.items()):
            run.cancel()
            await asyncio.gather(run, return_exceptions=True)
            self._forget(task_id)

    async def _drive(
        self,
        task_id: str,
        runner: Runner,
        goal: str,
        context: dict[str, Any] | None,
    ) -> None:
        handle = self._handles[task_id]
        try:
            result = await runner.run(goal, task_id=task_id, context=context)
        except Exception as exc:  # noqa: BLE001
            # The Runner converts its own failures into a status, so reaching
            # here means a handler misbehaved.
            handle.status = "failed"
            handle.diagnostic = f"运行意外中断：{exc}"
            self._forget(task_id)
            return
        finally:
            self._confirmations.pop(task_id, None)
            self._inputs.pop(task_id, None)
            self._runs.pop(task_id, None)
        self._apply(handle, result)
        try:
            self._store.record(result)
        except Exception as exc:  # noqa: BLE001
            # 运行确实结束了，所以它的终态仍然成立；缺的只是持久化副本，
            # 而逐步 trace 已经由 sink 落库。
            detail = result.diagnostic or "运行已结束"
            handle.diagnostic = f"{detail}；持久化失败：{exc}"

    def _apply(self, handle: RunHandle, result: RunResult) -> None:
        handle.status = result.status
        handle.step = result.state.step
        handle.diagnostic = result.diagnostic
        handle.pending_confirmation = None
        handle.pending_input = None

    def _forget(self, task_id: str) -> None:
        self._runs.pop(task_id, None)
        self._confirmations.pop(task_id, None)
        self._inputs.pop(task_id, None)

    async def _await_confirmation(
        self,
        task_id: str,
        action: str,
        arguments: Any,
        state: TaskState,
    ) -> bool:
        handle = self._handles.get(task_id)
        if handle is None:
            return False
        materialized = dict(arguments)
        digest = confirmation_digest(task_id, action, materialized)
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._confirmations[task_id] = future
        handle.status = AWAITING_CONFIRMATION
        handle.pending_confirmation = PendingConfirmation(
            action=action,
            arguments=materialized,
            step=state.step,
            digest=digest,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=self._settings.confirmation_ttl_seconds),
        )
        try:
            # 超过 TTL 就当作「没批准」：一个悬着的确认不该在几小时后悄悄生效。
            return await asyncio.wait_for(future, timeout=self._settings.confirmation_ttl_seconds)
        except asyncio.TimeoutError:  # 3.11 之前它不是内建 TimeoutError，用别名才两边都对
            return False
        finally:
            self._confirmations.pop(task_id, None)
            handle.pending_confirmation = None
            if handle.status == AWAITING_CONFIRMATION:
                handle.status = RUNNING

    async def _await_input(self, task_id: str, question: str, state: TaskState) -> str | None:
        handle = self._handles.get(task_id)
        if handle is None:
            return None
        future: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self._inputs[task_id] = future
        handle.status = AWAITING_INPUT
        handle.pending_input = PendingInput(question=question, step=state.step)
        try:
            return await future
        finally:
            self._inputs.pop(task_id, None)
            handle.pending_input = None
            if handle.status == AWAITING_INPUT:
                handle.status = RUNNING
