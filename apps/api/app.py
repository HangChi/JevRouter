from __future__ import annotations

import logging
import secrets
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
    PolicyThresholdView,
    PolicyView,
    ProvideInputRequest,
    RecordEvalRunRequest,
    RecordEvalRunResponse,
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskListResponse,
    TaskSummary,
    TaskView,
    ToolPolicyView,
    TraceListResponse,
    TraceView,
)
from apps.api.service import ConfirmationConflict, RunHandle, TaskService, UnknownTaskError
from apps.api.storage import TraceStore
from jev_router.policy import CONFIRMING_RISKS
from jev_router.tools import CalculatorTool, MockEmailTool, ToolRegistry, WriteFileTool

DEFAULT_TASK_LIMIT = 50
DEFAULT_EVAL_LIMIT = 20

logger = logging.getLogger(__name__)


def default_registry(settings: Settings) -> ToolRegistry:
    """不做额外装配时，一个部署会拿到的工具集。

    两个搜索工具不在其中，因为它们的文档需要调用方注入；需要时显式装配注册表。
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
    registry = tools if tools is not None else default_registry(resolved)
    service = TaskService(
        store=store,
        settings=resolved,
        tools=registry,
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
    app.state.tools = registry

    def get_service(request: Request) -> TaskService:
        service_instance: TaskService = request.app.state.service
        return service_instance

    def get_store(request: Request) -> TraceStore:
        store: TraceStore = request.app.state.store
        return store

    def require_token(request: Request) -> None:
        """配置了 ``JEV_API_TOKEN`` 就校验 Bearer；没配置则不拦。

        默认不拦是为了让本地仪表盘开箱可用——服务的职责边界是「默认只绑回环
        地址」，一旦要对外提供服务，必须同时设置 token。缺少 token 会在启动时
        打一条显式警告，而不是安静地以无鉴权模式运行。
        """
        expected = request.app.state.settings.api_token
        if expected is None:
            return
        header = request.headers.get("authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(presented, expected):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "缺少或错误的访问令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if resolved.api_token is None:
        logger.warning(
            "未设置 JEV_API_TOKEN：API 不做鉴权。请只绑定 127.0.0.1，"
            "对外提供服务前务必配置该变量。"
        )

    @app.post(
        "/tasks",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=SubmitTaskResponse,
        dependencies=[Depends(require_token)],
    )
    async def submit_task(
        body: SubmitTaskRequest, current: TaskService = Depends(get_service)
    ) -> SubmitTaskResponse:
        handle = current.submit(body.goal, context=body.context)
        return SubmitTaskResponse(task_id=handle.task_id, status=handle.status)

    @app.get("/tasks", response_model=TaskListResponse, dependencies=[Depends(require_token)])
    async def list_tasks(
        limit: int = DEFAULT_TASK_LIMIT, current: TaskService = Depends(get_service)
    ) -> TaskListResponse:
        if limit < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "limit 必须是正数")
        return TaskListResponse(
            tasks=[_summary(handle) for handle in current.list(limit=limit)]
        )

    @app.get(
        "/tasks/{task_id}", response_model=TaskView, dependencies=[Depends(require_token)]
    )
    async def get_task(task_id: str, current: TaskService = Depends(get_service)) -> TaskView:
        return _view(_lookup(current, task_id))

    @app.get(
        "/tasks/{task_id}/traces",
        response_model=TraceListResponse,
        dependencies=[Depends(require_token)],
    )
    async def get_traces(
        task_id: str, current: TaskService = Depends(get_service)
    ) -> TraceListResponse:
        _lookup(current, task_id)
        traces = current.traces(task_id)
        return TraceListResponse(
            task_id=task_id, traces=[TraceView.from_trace(trace) for trace in traces]
        )

    @app.post(
        "/tasks/{task_id}/confirm",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_token)],
    )
    async def confirm_task(
        task_id: str, body: ConfirmRequest, current: TaskService = Depends(get_service)
    ) -> None:
        _lookup(current, task_id)
        try:
            current.confirm(task_id, body.approved, body.digest)
        except ConfirmationConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @app.post(
        "/tasks/{task_id}/input",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_token)],
    )
    async def provide_input(
        task_id: str, body: ProvideInputRequest, current: TaskService = Depends(get_service)
    ) -> None:
        _lookup(current, task_id)
        try:
            current.provide_input(task_id, body.answer)
        except KeyError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "该任务当前没有在等待用户输入"
            ) from exc

    @app.post(
        "/evals",
        status_code=status.HTTP_201_CREATED,
        response_model=RecordEvalRunResponse,
        dependencies=[Depends(require_token)],
    )
    async def record_eval_run(
        body: RecordEvalRunRequest, store: TraceStore = Depends(get_store)
    ) -> RecordEvalRunResponse:
        store.record_eval_run(body)
        return RecordEvalRunResponse(
            run_id=body.run_id,
            case_count=len({outcome.case_id for outcome in body.outcomes}),
        )

    @app.get("/evals", response_model=EvalRunListResponse, dependencies=[Depends(require_token)])
    async def list_eval_runs(
        limit: int = DEFAULT_EVAL_LIMIT, store: TraceStore = Depends(get_store)
    ) -> EvalRunListResponse:
        if limit < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "limit 必须是正数")
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

    @app.get(
        "/evals/{run_id}", response_model=EvalRunView, dependencies=[Depends(require_token)]
    )
    async def get_eval_run(run_id: str, store: TraceStore = Depends(get_store)) -> EvalRunView:
        view = store.load_eval_run(run_id)
        if view is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到这次评测运行")
        return view

    @app.get("/policy", response_model=PolicyView, dependencies=[Depends(require_token)])
    async def get_policy(request: Request) -> PolicyView:
        current: Settings = request.app.state.settings
        registered: ToolRegistry = request.app.state.tools
        thresholds = current.policy_thresholds()
        return PolicyView(
            thresholds=PolicyThresholdView(
                confirmation=thresholds.confirmation,
                risk=thresholds.risk,
                reasoning=thresholds.reasoning,
                confidence=thresholds.confidence,
                completion=current.completion_threshold,
            ),
            tools=[
                ToolPolicyView(
                    name=name,
                    risk=registered.get(name).risk,
                    description=registered.get(name).description,
                    requires_confirmation=registered.get(name).risk in CONFIRMING_RISKS,
                )
                for name in registered.names()
            ],
            confirmation_ttl_seconds=current.confirmation_ttl_seconds,
            confirmation_binding="task + action + arguments",
        )

    return app


def _lookup(service: TaskService, task_id: str) -> RunHandle:
    try:
        return service.get(task_id)
    except UnknownTaskError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到该任务") from exc


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
                digest=confirmation.digest,
                expires_at=confirmation.expires_at.isoformat(),
            )
        ),
        pending_input=(
            None
            if user_input is None
            else PendingInputView(question=user_input.question, step=user_input.step)
        ),
    )

