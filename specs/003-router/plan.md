# 实现计划：决策路由层

## 摘要

新增一个仅提供建议的路由层（Router），它把可信的候选动作和任务状态打包进单个 Jev 请求，再把类型化答案映射为内部决策。它不实现策略，也不执行工具。

## 技术背景

- Python 包：`jev_router`。
- Jev 问题与答案：复用 `jev_router.clients.jev` 的类型化模型与校验。
- 候选：有序的 `ToolRegistry.names()` 及每个可信工具的描述，其后是固定的控制动作。
- 测试：pytest 与 `httpx.MockTransport`；无真实请求。
- 静态检查：Ruff 与严格模式的 mypy。

## 设计

`Router.route(state)` 提交单个请求，其中包含一个在已注册工具以及 `ask_user`、`delegate_to_llm` 和 `finish` 之间做选择的 choice 问题、一个五级风险评分问题，以及两个 Noul 问题。它把答案取值和置信度字段映射为不可变的 `RouteDecision`。注册表只被查询名称／元数据；其执行方法绝不会被调用。不做任何策略阈值或授权决策。

## 非目标

- 策略引擎或阈值决策。
- 工具执行、智能体循环、验证器、API、仪表盘或持久化。
- 模型发现、重试，或对 Jev 客户端契约的改动。

## 验证策略

运行 `uv run ruff check .`、`uv run mypy jev_router` 和 `uv run pytest`。验证单次请求、全部四种问题类型、固定动作候选、有序风险图例、答案映射、类型化客户端错误、空注册表行为，以及不发生工具执行。
