# 实现计划：有界执行循环（Runner）

## 概述

新增 `jev_router/runner.py`：一个由现有路由层、策略引擎、TaskState/预算与验证器构成的有界循环，并为核心本身无法执行的动作提供可注入的协作者。

## 技术背景

- 核心包：`jev_router`。
- 既有公开决策：`RouteDecision`、`PolicyDecision`/`PolicyOutcome`、`VerificationDecision`。
- 既有状态契约：`TaskState.advance()`、`ExecutionBudget.consume_step()/consume_model_call()`。
- 提供商边界：`JevClient.systemone` 使用 `json.dumps(allow_nan=False)` 校验载荷，因此路由载荷必须是纯 JSON。
- 遗留义务：`specs/004-policy/plan.md` 中粗略的 `Tool.risk` 分类未被强制执行；`docs/security.md` 要求执行循环（Runner）加以应用。
- 测试：使用 `httpx.MockTransport` 的离线 pytest；不发起线上请求。

## 设计

`Runner.__init__` 接收 `client`、`model`、`tools`、`budget`、`completion_threshold` 以及四个可选的协作者，然后自行构造 `Router`、`PolicyEngine` 与 `Verifier`。在内部完成组装，使「共享单个 `ToolRegistry`」成为结构性约束而非惯例，因此执行时的注册复查无法被一个不一致的实例绕过。

协作者是 `Protocol`，以便测试进行打桩：

| 协议 | 方法 | 缺失时的行为 |
| --- | --- | --- |
| `ActionInputResolver` | `resolve(action, state) -> Mapping` | 产出 `{}`；工具自身的 schema 会拒绝它 |
| `ConfirmationHandler` | `confirm(task_id, action, arguments, state) -> bool` | `needs_confirmation` |
| `UserInputHandler` | `request_input(question, state) -> str \| None` | `needs_user_input` |
| `DelegateHandler` | `delegate(state) -> str` | `failed` |
| `TraceSink` | `emit(trace)` | 不做实时投递；trace 保留在 `RunResult.traces` 中 |

`ActionInputResolver` 之所以存在，是因为 `RouteDecision` 只携带动作名而不携带参数，而参数合成是 LLM 的职责，本阶段刻意不实现。它是可选的而非必需的，这样执行循环（Runner）不会强制引入 LLM 依赖；默认的 `{}` 会经由每个工具自身的输入 schema 按失败关闭。

循环在消耗任一计数器之前先检查两个预算计数器，因此停止永远不会发生在部分消耗之后。`execute`/`ask_confirmation` 先解析参数，再确认，最后执行——相反的顺序会让用户在批准某个动作的同时实际运行了不同的参数，而这是 `docs/security.md` 所禁止的。`_needs_confirmation` 将策略的 `ask_confirmation` 结果与 `tool.risk in {"write", "external"}` 做逻辑或。

一个私有的 `_Stop` 异常把终态从深层嵌套的迭代代码中带出，从而只保留一个 `_settle` 位置来封闭最终 trace 并构建 `RunResult`。`_verify` 返回 `_Verified` 值而不是抛出异常，因为「验证判定未完成」是正常结果而非错误。

`_verify` 还会检测无进展：`advance()` 返回新的 `TaskState`，因此 `verified is state` 能可靠地识别出对同一未变化快照的第二次否定评估，并以 `failed` 停止，而不是重新路由相同的载荷。

构造时会校验 `max_model_calls >= 2 * max_steps`，因为一个执行迭代需要一次路由加一次验证。缺少该校验时，一次运行可能对本可完成的任务报告 `budget_exhausted`。

## 受控重构

`jev_router/serialization.py` 新增 `jsonable(value)`，从 `verifier._jsonable` 原样提取。`verifier.py` 导入它；执行循环（Runner）在路由载荷中复用它。行为不变，且 `tests/test_verifier.py` 锁定了验证器的载荷结构。

## 非目标

- 执行循环（Runner）的持久化、`TaskState` 上的任务身份，或 trace 的序列化。
- LLM 适配器、模型发现、重试或 Jev 客户端变更。
- 阈值校准或按工具的策略覆盖。

## 验证策略

运行 `uv run ruff check .`、`uv run mypy jev_router` 与 `uv run pytest`。覆盖完成与继续、结束路径、预算耗尽、按工具风险的确认门控、参数绑定、委托、用户输入、每一种失败模式、trace 输出与不可变性。
