from __future__ import annotations

import asyncio
from dataclasses import dataclass
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

_DELEGATE_SYSTEM = (
    "You are the reasoning delegate of an agent. The router decided that this "
    "step needs deeper reasoning than a typed decision can provide. Produce the "
    "answer or the concrete content that advances the task, as plain text."
)

_RESULT_LIMIT = 500


class UnknownTaskError(KeyError):
    """Raised when a task id is not known to this process."""


@dataclass
class PendingConfirmation:
    action: str
    arguments: dict[str, Any]
    step: int


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
    """Binds one run's blocking requests to its task id.

    ``ConfirmationHandler`` receives the task id but ``UserInputHandler`` does
    not, so both are routed through a per-run adapter that already knows it.
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
    """Drives runs in the background and exposes them to HTTP handlers.

    A run outlives the request that started it, so confirmation and user input
    are resolved by later requests through futures rather than by blocking. The
    Runner itself is unchanged: it simply awaits a handler that happens to wait
    for a human.
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
        # An explicitly injected resolver wins: it is the caller's own seam (the
        # tests use it), and the LLM-backed one is the fallback for a deployment
        # that configures nothing else.
        self._delegate, llm_resolver = self._build_llm_collaborators(llm_client)
        self._resolver = resolver if resolver is not None else llm_resolver
        self._handles: dict[str, RunHandle] = {}
        self._confirmations: dict[str, asyncio.Future[bool]] = {}
        self._inputs: dict[str, asyncio.Future[str | None]] = {}
        self._runs: dict[str, asyncio.Task[None]] = {}

    def _build_llm_collaborators(
        self, llm_client: LLMClient | None
    ) -> tuple[LLMDelegate | None, LLMArgumentResolver | None]:
        """Assemble the delegate and the argument resolver from one LLM config.

        Without LLM settings the service stays fail closed exactly as phase 7
        shipped it: a delegation request stops the run, and a tool call resolves
        to no arguments so the tool's own schema refuses it. One configuration
        drives both, because an agent that can reason but not parameterize is
        not useful.
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
            raise ValueError(f"task {identifier!r} is already known")
        handle = RunHandle(task_id=identifier, goal=goal, status=RUNNING)
        self._handles[identifier] = handle
        runner = Runner(
            client=self._client,
            model=self._settings.model,
            tools=self._tools,
            budget=self._settings.budget(),
            completion_threshold=self._settings.completion_threshold,
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
            raise ValueError("limit must be positive")
        return tuple(reversed(list(self._handles.values())))[:limit]

    def traces(self, task_id: str) -> tuple[StepTrace, ...]:
        self.get(task_id)
        return self._store.load_traces(task_id)

    def confirm(self, task_id: str, approved: bool) -> None:
        self.get(task_id)
        future = self._confirmations.get(task_id)
        if future is None or future.done():
            raise UnknownTaskError(f"task {task_id!r} is not awaiting confirmation")
        future.set_result(approved)

    def provide_input(self, task_id: str, answer: str) -> None:
        self.get(task_id)
        future = self._inputs.get(task_id)
        if future is None or future.done():
            raise UnknownTaskError(f"task {task_id!r} is not awaiting user input")
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
            handle.diagnostic = f"the run stopped unexpectedly: {exc}"
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
            # The run did finish, so its status stands; only the durable copy is
            # missing, and the sink already wrote the individual steps.
            detail = result.diagnostic or "the run finished"
            handle.diagnostic = f"{detail}; persistence failed: {exc}"

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
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._confirmations[task_id] = future
        handle.status = AWAITING_CONFIRMATION
        handle.pending_confirmation = PendingConfirmation(
            action=action, arguments=dict(arguments), step=state.step
        )
        try:
            return await future
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
