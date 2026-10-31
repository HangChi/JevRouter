# 数据模型：有界执行循环（Runner）

## RunStatus

一次运行的终态：

- `completed`：验证器的完成概率达到阈值，或在任何步骤运行之前就收到了 `finish` 推荐。
- `needs_user_input`：策略请求了更多信息，但没有提供。
- `needs_confirmation`：需要确认，但确认缺失、被拒绝，或没有处理器。
- `rejected`：推荐的动作未注册（或不再注册）。
- `budget_exhausted`：在循环能够结束之前，步数或模型调用额度已用尽。
- `failed`：提供商错误、工具输入被拒绝、状态被拒绝或协作者缺失导致运行停止。

## RunResult

`Runner.run()` 的不可变结果：

- `status`：终态 `RunStatus`。
- `task_id`：调用方提供的标识符，或自动生成的标识符。
- `state`：最终的 `TaskState` 快照。
- `budget`：剩余的 `ExecutionBudget`。
- `traces`：有序的 `StepTrace` 记录，对于已启动的运行从不为空。
- `diagnostic`：人类可读的原因，对每一个非 completed 状态都会存在。

## StepTrace

一次迭代的不可变记录：

- `step`、`task_id`、`action`：位置与推荐的动作。
- `executed`：是否调用了已注册的工具。`ask_user` 与 `delegate_to_llm` 会使其保持 `false`，因为它们不产生副作用。
- `result`：该步骤产生的任何内容（工具输出、用户输入或委托得来的文本）。
- `policy_outcome`、`policy_reason`：本地授权结果。
- `route_confidence`、`route_risk`、`requires_confirmation`、`needs_reasoning`：提供商返回的概率。
- `confirmed`：批准决定；若无需批准则为 `null`。
- `arguments`：绑定到该确认的解析后参数映射。
- `verification`：若执行了验证，则为 `VerificationDecision`。
- `state_snapshot`：本步骤发送给提供商的 JSON 载荷。
- `model`：提供商的模型标识符。
- `duration_ms`：迭代的墙钟耗时。

路由字段可为 null，因为在做出决策之前就停止的路径（预算耗尽、提供商失败）没有任何路由字段。

## 协作者

由调用方注入的协议。`ActionInputResolver` 是参数合成的接缝，而参数合成属于本阶段之外的 LLM 职责；其默认值 `{}` 会被每个工具自身的输入 schema 拒绝，因此缺失解析器时会按失败关闭，而不是带着臆造的参数执行。

## 预算

`ExecutionBudget` 未改动。执行循环（Runner）每次迭代消耗一步，每次路由、验证与委托消耗一次模型调用。构造时要求 `max_model_calls >= 2 * max_steps`。由于每步至少消耗两次模型调用，`_verify` 与委托分支中的模型调用检查是防御性的：在该不变式下，步数会先耗尽或同时耗尽。
