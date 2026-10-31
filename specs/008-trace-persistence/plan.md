# 实施计划：trace 持久化

## 摘要

新增 `apps/api/storage.py`：一个 SQLite `TraceStore`，持久化 Runner 已经产出的 `RunResult` 与 `StepTrace` 值，另加一个用于仍在进行中的运行的增量 sink。

## 技术背景

- 核心包：`jev_router`（本阶段不做改动）。
- 新位置：`apps/api/`，因为 `docs/development.md` 声明核心包避免数据库实现，而 `docs/architecture.md` 把存储列在 `apps/api/` 之下。
- 输入契约：`RunResult`（status、task_id、state、budget、traces、diagnostic）与 `StepTrace`。
- JSON 转换：`jev_router.serialization.jsonable`，已由验证器与 Runner 共用。
- 存储：标准库 `sqlite3`；不新增依赖，也不改动第 7 阶段的同步 `TraceSink` 契约。
- 测试：针对临时数据库文件的离线 pytest。

## 设计

三张表对应三个 trace 概念。`tasks` 为每次运行保留一行，记录其终态状态、步骤数、诊断信息与最终状态。`agent_steps` 为每个 `StepTrace` 保留一行。`evaluations` 单独保存 `VerificationDecision`，以 `(task_id, step)` 为键，这样评估结果不会在步骤行内部重复一份。

`PRAGMA user_version` 记录模式版本；打开版本更新的数据库会被拒绝，而不是被迁移。每个 JSON 列都存储 `{"version": N, "data": ...}`，这样未来某处的载荷变化会按值被检测到，而不是被静默误读。

两条写入路径共用一个 `_write_step` upsert：

- `record(result)` 在一个事务内写入终态任务行与全部 trace。
- `sink()` 返回一个 `TraceSink`，在首次发出时 upsert 一行 `running` 任务，并在每个步骤到达时写入该步骤，这样即使进程被杀掉，也仍留下可读的 trace。

两者对重复的 `(task_id, step)` 都是幂等的，因此在 `sink()` 之后调用 `record()` 会完成定稿而不会重复写入。

读取会重建原始的值：`load_traces` 把步骤与评测连接起来并返回 `StepTrace` 对象，`load_task` 返回 `TaskRecord`。往返测试断言其与 Runner 自身的值相等。

编码做降级处理而不是失败。工具在其输出被接受之前就已运行，因此一条 trace 可能持有一个 `TaskState.advance` 已经拒绝的值；`_degrade` 只把出问题的叶子替换为 `{"__unserializable__": ...}`，并保持这次运行的其余部分可读。非有限浮点数获得同样的处理，因为 `json.dumps(allow_nan=False)` 否则会拒绝整次写入。

一个可选的 `redact` 回调在编码之前作用于结果、参数与状态快照。这正是 `docs/security.md` 在持久化用户目标与工具 I/O 之前所要求的钩子；保留与删除策略仍不在范围内。

凭据保证是结构性的：存储只会看到 `RunResult`/`StepTrace`，永远不会看到 `JevClientConfig`。一个测试用一个哨兵密钥驱动真实的 `Runner`，并断言这些字节不会出现在数据库文件中。

连接在 `__init__` 中创建，由 `close()` 或上下文管理器关闭。写入是同步且短暂的，与同步的 `TraceSink` 相匹配；该存储被记录为单线程，并由单个事件循环驱动。

## 非目标

- HTTP 层、任务提交或确认流程。
- 保留、删除或访问控制。
- 模式迁移。
- 异步驱动、后台写入器或连接池。

## 验证策略

运行 `uv run ruff check .`、`uv run mypy jev_router apps` 以及 `uv run pytest`。覆盖往返相等性、完成前的增量写入、载荷与模式的版本化、脱敏、降级、任务隔离、幂等性以及凭据保证。
