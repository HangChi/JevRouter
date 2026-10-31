# 数据模型：API HTTP 边界

## 状态

两套词汇，刻意分开：

- **终态** —— 来自核心包的 `RunStatus`：`completed`、`needs_user_input`、`needs_confirmation`、`rejected`、`budget_exhausted`、`failed`。
- **实时** —— 定义在 `apps/api/schemas.py` 中，用于尚未结束的运行：`running`、`awaiting_confirmation`、`awaiting_input`。

`TraceStore` 也把 `running` 用作其存储标记，用于那些 trace 仍在写入的任务；`record()` 会用终态状态替换它。两种用法重合。

## RunHandle

一次运行的内存记录，由 `TaskService` 持有：

- `task_id`、`goal`、`status`、`step`、`diagnostic`。
- `pending_confirmation`：`PendingConfirmation(action, arguments, step)` 或 `None`。
- `pending_input`：`PendingInput(question, step)` 或 `None`。

句柄不会被持久化。进程重启会丢失在途的运行；它们的 trace 仍留在 SQLite 中。

## Futures

`TaskService` 持有确认与输入的 `dict[str, asyncio.Future]`，以任务 id 为键。一次运行是顺序的，因此每个任务最多各有一个待处理项。这些 future 会在 `_drive` 的 `finally` 中以及 `shutdown()` 时被丢弃。

## Settings

由 `from_env()` 构建的冻结 pydantic 模型：

| 字段 | 环境变量 | 默认值 |
| --- | --- | --- |
| `model` | `JEV_MODEL`（必填） | — |
| `database_path` | `JEV_DATABASE_PATH` | `traces.db` |
| `workspace_root` | `JEV_WORKSPACE_ROOT` | `./workspace` |
| `max_steps` | `JEV_MAX_STEPS` | `8` |
| `max_model_calls` | `JEV_MAX_MODEL_CALLS` | `16` |
| `completion_threshold` | `JEV_COMPLETION_THRESHOLD` | `0.75` |
| `jev` | `JEV_API_KEY`、`JEV_BASE_URL`、`JEV_TIMEOUT_SECONDS` | 厂商默认值 |

校验：空白字符串被拒绝，`max_steps >= 1`，`completion_threshold` 在 `[0, 1]` 之内，且 `max_model_calls >= 2 * max_steps`。非数值的数值字段会连同变量名一起报错。

## 端点

| 方法 | 路径 | 成功 | 错误 |
| --- | --- | --- | --- |
| POST | `/tasks` | `202` `SubmitTaskResponse` | `422` |
| GET | `/tasks` | `200` `TaskListResponse` | `limit < 1` 时为 `400` |
| GET | `/tasks/{id}` | `200` `TaskView` | `404` |
| GET | `/tasks/{id}/traces` | `200` `TraceListResponse` | `404` |
| POST | `/tasks/{id}/confirm` | `204` | `404`、`409`、`422` |
| POST | `/tasks/{id}/input` | `204` | `404`、`409`、`422` |

`GET /tasks` 按最新在前返回，与 `TraceStore.list_tasks` 一致。

## TraceView

为传输而把 `StepTrace` 扁平化：路由概率、策略结果、执行结果、参数、从 `VerificationDecision` 中取出的完成概率与质量评分，以及状态快照。之所以包含 `state_snapshot`，是因为那正是供应商实际看到的内容。

## 默认注册表

`default_registry(settings)` 注册 `calculator`、`write_file`（位于 `workspace_root` 之下）与 `send_mock_email`。两个搜索工具被略去，因为它们需要由调用方注入文档。
