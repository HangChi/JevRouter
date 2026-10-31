# 实施计划：API HTTP 边界

## 摘要

新增 `apps/api/{config,schemas,service,app}.py`：一个 FastAPI 应用，在后台启动运行，通过后续请求来处理它们的确认与输入提示，并从 SQLite 存储中提供 trace。

## 技术背景

- 核心包：`jev_router`（未改动）。
- 既有的 API 层模块：第 8 阶段的 `apps/api/storage.py`。
- Runner 契约：`Runner(..., confirmation=..., user_input=..., trace_sink=...)` 与 `RunResult`。
- HTTP：FastAPI 配合 uvicorn；两者在本阶段都作为运行时依赖加入。
- 测试：`fastapi.testclient.TestClient` 针对临时数据库；不涉及网络。

## 设计

四个模块，各司一职：

- `config.py` —— 一个冻结的 `Settings` pydantic 模型，外加 `from_env()`。一切都在启动时被校验一次，包括 `max_model_calls >= 2 * max_steps`，因此配置错误的部署会拒绝提供服务，而不是在第一个任务上失败。Jev 部分复用已经测试过的 `JevClientConfig.from_env()`。
- `schemas.py` —— 严格的请求/响应模型（`extra="forbid"`）以及实时状态常量。
- `service.py` —— `TaskService`，即运行注册表。
- `app.py` —— 应用工厂、路由与错误映射。

### 后台运行与 future

`TaskService.submit()` 构建一个 Runner，其 `ConfirmationHandler` 与 `UserInputHandler` 是绑定到该任务 id 的每次运行专属适配器，然后用 `create_task` 调度 `_drive()`。请求立即返回。

由于 `UserInputHandler.request_input` 不接收任务 id，两个处理器都经由一个已经知道该 id 的 `_RunHandlers` 适配器。

每个处理器在服务上注册一个 `asyncio.Future`，把句柄切换为 `awaiting_confirmation` / `awaiting_input`，然后等待。`POST /tasks/{id}/confirm` 与 `POST /tasks/{id}/input` 会兑现相应的 future。Runner 未被改动：它只是等待一个恰好正在等人回应的处理器。

这一点很重要，因为停止再重启的设计会重新执行之前步骤的副作用。让运行保持存活可以完全避免这一点。

### 路由处理器是异步的

处理器被声明为 `async def`，这样 `submit()` 内部的 `asyncio.get_running_loop()` 才能成功。FastAPI 会把同步处理器放到线程池中运行，那里没有正在运行的事件循环。

### 实时状态与终态状态

`RunStatus` 描述的是已结束的运行。在途的运行还需要另外三个状态，定义在 `schemas.py` 中：`running`、`awaiting_confirmation`、`awaiting_input`。句柄携带实时状态；`record()` 会用在终态状态替换已存储的 `running` 标记。

### 阻塞期间的 trace 发出

在等人回应的步骤尚未完成，因此 Runner 还没有发出它的 trace。待处理的内容由任务视图报告（`pending_confirmation` / `pending_input`），而不是由 trace 列表报告。这样保持每个已完成步骤一条 trace，而不是发出不完整的记录。

### 错误映射

- 未知任务 id → 在每一个任务范围内的路由上返回 `404`。
- 在没有待处理事项时调用提示端点 → `409`。
- 未通过严格模式的请求体 → 由 FastAPI 的校验返回 `422`。
- `GET /tasks?limit=0` → `400`。

### 持久化失败不等于运行失败

`record()` 在句柄已经被更新为该运行真实的终态状态之后才被调用。如果它抛出异常，状态依然成立，诊断信息会记录持久化失败——sink 早已写入了各个步骤。真到这里出现异常，只意味着存储本身坏了。

## 非目标

- 认证、限流、多租户、取消或重启恢复。
- 流式响应或 Web 看板。
- 对核心包的改动。

## 验证策略

运行 `uv run ruff check .`、`uv run mypy jev_router apps` 以及 `uv run pytest`。覆盖每个端点、每种错误映射、确认与输入的往返、列表排序、启动校验以及凭据保证。另外在 uvicorn 下针对临时数据库启动应用，并用 curl 实际调用这些端点。
