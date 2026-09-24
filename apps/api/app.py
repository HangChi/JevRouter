from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status

from apps.api.config import Settings
from apps.api.schemas import (
    ConfirmRequest,
    EvalRunListResponse,
    EvalRunSummary,
    EvalRunView,
    PendingConfirmationView,
    PendingInputView,
    ProvideInputRequest,
    RecordEvalRunRequest,
    RecordEvalRunResponse,
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskListResponse,
    TaskSummary,
    TaskView,
    TraceListResponse,
    TraceView,
)
from apps.api.service import RunHandle, TaskService, UnknownTaskError
from apps.api.storage import TraceStore
from jev_router.tools import CalculatorTool, MockEmailTool, ToolRegistry, WriteFileTool

DEFAULT_TASK_LIMIT = 50
DEFAULT_EVAL_LIMIT = 20


def default_registry(settings: Settings) -> ToolRegistry:
    """The tool set a deployment gets without further wiring.

    The two search tools are omitted because they need documents injected by the
    caller; assemble the registry explicitly when they are wanted.
    """
    return ToolRegistry(
        [
            CalculatorTool(),
            WriteFileTool(settings.workspace_root),
            MockEmailTool(),
        ]
    )


def create_app(
    settings: Settings | None = None,
    *,
    store: TraceStore | None = None,
    tools: ToolRegistry | None = None,
    resolver: Any = None,
    client: Any = None,
    llm_client: Any = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    owns_store = store is None
    if store is None:
        store = TraceStore(resolved.database_path)
    service = TaskService(
        store=store,
        settings=resolved,
        tools=tools if tools is not None else default_registry(resolved),
        resolver=resolver,
        client=client,
        llm_client=llm_client,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.service = service
        try:
            yield
        finally:
            await service.shutdown()
            if owns_store:
                store.close()

    app = FastAPI(title="JevRouter", version="0.1.0", lifespan=lifespan)
    app.state.service = service
    app.state.store = store
    app.state.settings = resolved

    def get_service(request: Request) -> TaskService:
        service_instance: TaskService = request.app.state.service
        return service_instance

    def get_store(request: Request) -> TraceStore:
        store: TraceStore = request.app.state.store
        return store

    @app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, response_model=SubmitTaskResponse)
    async def submit_task(
        body: SubmitTaskRequest, current: TaskService = Depends(get_service)
    ) -> SubmitTaskResponse:
        handle = current.submit(body.goal, context=body.context)
        return SubmitTaskResponse(task_id=handle.task_id, status=handle.status)

    @app.get("/tasks", response_model=TaskListResponse)
    async def list_tasks(
        limit: int = DEFAULT_TASK_LIMIT, current: TaskService = Depends(get_service)
    ) -> TaskListResponse:
        if limit < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "limit must be positive")
        return TaskListResponse(
            tasks=[_summary(handle) for handle in current.list(limit=limit)]
        )
    @app.get("/tasks/{task_id}", response_model=TaskView)
    async def get_task(task_id: str, current: TaskService = Depends(get_service)) -> TaskView:
        return _view(_lookup(current, task_id))

    @app.get("/tasks/{task_id}/traces", response_model=TraceListResponse)
    async def get_traces(task_id: str, current: TaskService = Depends(get_service)) -> TraceListResponse:
        _lookup(current, task_id)
        traces = current.traces(task_id)
        return TraceListResponse(
            task_id=task_id, traces=[TraceView.from_trace(trace) for trace in traces]
        )

    @app.post("/tasks/{task_id}/confirm", status_code=status.HTTP_204_NO_CONTENT)
    async def confirm_task(
        task_id: str, body: ConfirmRequest, current: TaskService = Depends(get_service)
    ) -> None:
        _lookup(current, task_id)
        try:
            current.confirm(task_id, body.approved)
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "the task is not awaiting confirmation"
            ) from exc

    @app.post("/tasks/{task_id}/input", status_code=status.HTTP_204_NO_CONTENT)
    async def provide_input(
        task_id: str, body: ProvideInputRequest, current: TaskService = Depends(get_service)
    ) -> None:
        _lookup(current, task_id)
        try:
            current.provide_input(task_id, body.answer)
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "the task is not awaiting user input"
            ) from exc

    @app.post("/evals", status_code=status.HTTP_201_CREATED, response_model=RecordEvalRunResponse)
    async def record_eval_run(
        body: RecordEvalRunRequest, store: TraceStore = Depends(get_store)
    ) -> RecordEvalRunResponse:
        store.record_eval_run(body)
        return RecordEvalRunResponse(
            run_id=body.run_id,
            case_count=len({outcome.case_id for outcome in body.outcomes}),
        )

    @app.get("/evals", response_model=EvalRunListResponse)
    async def list_eval_runs(
        limit: int = DEFAULT_EVAL_LIMIT, store: TraceStore = Depends(get_store)
    ) -> EvalRunListResponse:
        if limit < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "limit must be positive")
        return EvalRunListResponse(
            runs=[
                EvalRunSummary(
                    run_id=record.run_id,
                    mode=record.mode,
                    created_at=record.created_at,
                    case_count=record.case_count,
                )
                for record in store.list_eval_runs(limit=limit)
            ]
        )

    @app.get("/evals/{run_id}", response_model=EvalRunView)
    async def get_eval_run(run_id: str, store: TraceStore = Depends(get_store)) -> EvalRunView:
        view = store.load_eval_run(run_id)
        if view is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "eval run not found")
        return view

    return app


def _lookup(service: TaskService, task_id: str) -> RunHandle:
    try:
        return service.get(task_id)
    except UnknownTaskError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found") from exc


def _summary(handle: RunHandle) -> TaskSummary:
    return TaskSummary(
        task_id=handle.task_id, goal=handle.goal, status=handle.status, step=handle.step
    )


def _view(handle: RunHandle) -> TaskView:
    confirmation = handle.pending_confirmation
    user_input = handle.pending_input
    return TaskView(
        task_id=handle.task_id,
        goal=handle.goal,
        status=handle.status,
        step=handle.step,
        diagnostic=handle.diagnostic,
        pending_confirmation=(
            None
            if confirmation is None
            else PendingConfirmationView(
                action=confirmation.action,
                arguments=confirmation.arguments,
                step=confirmation.step,
            )
        ),
        pending_input=(
            None
            if user_input is None
            else PendingInputView(question=user_input.question, step=user_input.step)
        ),
    )
