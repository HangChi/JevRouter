# 实现计划：策略引擎

## 摘要

新增一个确定性的本地策略门控，它消费 `RouteDecision` 并返回类型化结果，不执行工具。

## 技术背景

- 核心包：`jev_router`。
- 路由层契约：`jev_router.router.RouteDecision`。
- 可信工具允许列表：`ToolRegistry.names()`。
- MVP 阈值与优先级：`doc.md` 第 5 节。
- 测试：离线 pytest；不需要 Jev 请求。

## 设计

`PolicyEngine` 接收一个 `ToolRegistry`，并对单条 `RouteDecision` 求值。控制动作映射到 `ASK_USER`、`DELEGATE_TO_LLM` 和 `FINISH`。未知或已不再注册的工具动作产出 `REJECT`。对于已注册的工具动作，先检查确认概率 > 0.75 或风险 >= 2.5，再检查推理概率 > 0.70 或动作置信度 < 0.75，否则产出 `EXECUTE`。`PolicyDecision` 是不可变的，包含其结果、原始动作和简明原因。`EXECUTE` 结果仅授权由调用方控制的下一个步骤；策略引擎既不调用工具，也不提供用户的显式确认。

阈值是 MVP 默认值，而非厂商指引。粗粒度的 `Tool.risk` 分类在本阶段不引入任何未被要求的策略行为。

## 非目标

- 工具执行或调用方确认工作流。
- 阈值标定、配置服务，或按工具覆盖。
- 执行循环（Runner）、验证器、持久化、API、仪表盘或真实集成。

## 验证策略

运行 `uv run ruff check .`、`uv run mypy jev_router` 和 `uv run pytest`。覆盖所有结果、阈值相等、优先级、未知与已移除工具，以及不发生执行。
