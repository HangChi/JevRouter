# 实现计划：Jev 验证器

## 概述

新增一个小型异步适配器，在一次请求中向 Jev 询问：最新的任务结果是否满足其目标，以及该结果有多大用处。它只返回评估；编排与停止/继续策略仍不在本阶段范围内。

## 技术背景

- 客户端：`jev_router.clients.jev.JevClient.systemone`。
- 输入：不可变的 `jev_router.state.TaskState`。
- 类型化问题/答案：既有的 `NoulQuestion`/`NoulAnswer` 与 `ScoreQuestion`/`ScoreAnswer`。
- 测试：离线 mock `JevClient.systemone`；不要调用线上服务。

## 设计

`Verifier` 接收一个客户端与显式的模型标识符。`verify(state)` 会检查至少存在一步且存在最新结果，然后构造 JSON 兼容的状态，包含目标、当前步、最新动作/结果、上下文与历史。一次 system-one 请求要求给出完成概率以及 2–4 级的质量分。冻结的 `VerificationDecision` 保留完成概率、质量分及其置信度和图例，以及响应模型。完成概率高或低本身都不会产生 `finish`、另一条路由或状态转换。

## 非目标

- 执行循环（Runner）、重试、执行或预算消耗。
- 完成度阈值、策略或状态修改。
- 持久化、trace 存储、API、仪表盘或线上服务集成。

## 验证策略

运行 `uv run ruff check .`、`uv run mypy jev_router` 与 `uv run pytest`。断言精确的问题/请求结构、仅一次请求、答案映射、I/O 之前对缺失结果的拒绝、已净化的提供商失败，以及不发生修改。
