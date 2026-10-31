# 数据模型：trace 持久化

## 表

### tasks

每次运行一行。

- `task_id`：主键，与 `RunResult.task_id` 对应。
- `goal`：最初的目标。
- `status`：终态的 `RunStatus`；当 sink 仍在写入时则是 `running`。
- `step`：来自最终 `TaskState` 的已完成步骤数。
- `diagnostic`：`RunResult.diagnostic`，可为空。
- `created_at`、`updated_at`：带时区的 UTC ISO-8601 时间戳。
- `final_state`：goal、step、context、history 与最后结果组成的带版本 JSON。

### agent_steps

每个 `StepTrace` 一行，主键为 `(task_id, step)`，从 `tasks` 级联。

- `action`、`policy_outcome`、`policy_reason`。
- `route_confidence`、`route_risk`、`requires_confirmation`、`needs_reasoning`：可为空，因为在决策之前就停止的步骤没有路由结果。
- `confirmed`：可为空的整数（不需要确认时为 `NULL`）。
- `executed`：整数布尔值。
- `result`、`arguments`、`state_snapshot`：带版本 JSON，编码前已脱敏。
- `model`、`duration_ms`。

### evaluations

每次验证一行，主键为 `(task_id, step)`，从 `tasks` 级联。

- `completion_probability`、`quality_score`、`quality_confidence`。
- `quality_legend`：有序标签组成的 JSON 数组。
- `model`。

评估结果放在这里而不是 `agent_steps` 中，这样步骤行不必重复；`load_traces` 将两者连接起来。

## 版本化

两个相互独立的版本：

- **模式版本** —— `PRAGMA user_version`，当前为 `1`。打开版本值更新的数据库会被拒绝。
- **载荷版本** —— 内嵌在每个 JSON 列中，形如 `{"version": 1, "data": ...}`。版本未知的值，或者根本不是带版本信封的值，在读取时会被拒绝。

两者都不会被自动迁移。拒绝是安全的默认做法：静默误读会破坏 trace 记录。

## 降级

当一个值无法序列化时，`_encode` 回退到 `_degrade`。`_degrade` 遍历结构并只替换出问题的叶子：

- 无法序列化的对象变为 `{"__unserializable__": "<type name>"}`；
- 非有限浮点数变为 `{"__unserializable__": "non-finite float"}`。

该值中其余的一切都被保留，因此单个坏掉的工具输出不会让整次运行付出代价。

## TaskRecord

由 `load_task` 与 `list_tasks` 返回的读取模型：`task_id`、`goal`、`status`、`step`、`diagnostic`、`created_at`、`updated_at`、`final_state`。

## 运行中状态

`RUNNING_STATUS = "running"` 是持久化层面的标记，用于那些 trace 仍在写入的任务。它不属于 `RunStatus`；`record()` 会用终态状态替换它。
