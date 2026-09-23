# 开发与验证约定

## 项目状态

第一阶段建立了 `jev_router.clients.jev` 中的异步 TypeSafe Jev client，仅覆盖文档确认的 `POST /v1/systemone` 以及 `noul`、`choice`、`score` 三种 typed question。调用方显式提供 model identifier；模型发现不属于本阶段范围。项目使用 `pyproject.toml` 和 `uv.lock` 管理依赖。

## 安装与检查

```sh
uv sync --all-groups
uv run ruff check .
uv run mypy jev_router
uv run pytest
```

测试使用 HTTPX mock transport，不访问网络、不需要真实凭证，也不产生 billable requests。

## 工具层

`jev_router.tools` 提供可信应用代码配置的 `ToolRegistry` 和五个离线 MVP 工具：calculator、knowledge_search、web_search mock、write_file、send_mock_email mock。工具通过同步 `execute(input)` 接口返回 `ToolResult` 并声明 `read`、`write` 或 `external` 风险；该注册表只负责白名单注册、查找和调用，不包含路由或策略授权。搜索数据由调用方注入，邮件只生成模拟结果，均不访问网络。`WriteFileTool` 必须配置根目录，默认拒绝覆盖。

## Router

`jev_router.Router` 基于调用方提供的任务状态、模型标识和 `ToolRegistry`，一次性请求下一动作、风险、确认需求及推理需求，并返回 `RouteDecision`。动作候选由注册工具和 `ask_user`、`delegate_to_llm`、`finish` 组成。Router 仅提供建议，不授权、不执行工具；本地决策由 Policy Engine 完成。

## Policy Engine

`jev_router.PolicyEngine` 将 `RouteDecision` 映射为显式控制结果，不执行工具。MVP 初始阈值为 `requires_confirmation > 0.75` 或 `risk >= 2.5` 时请求确认；否则 `needs_reasoning > 0.70` 或动作置信度 `< 0.75` 时委托 LLM；其余已注册工具动作才返回 `execute`。`ask_user`、`delegate_to_llm`、`finish` 是对应控制分支，未注册动作拒绝。阈值是项目初值而非服务商推荐，应由 eval 校准。`execute` 不是执行调用；确认结果仍需调用方获取明确的用户批准。

调用方通过 `JevClientConfig.from_env()` 构造配置，并将模型名传给 `JevClient.systemone(model=..., state=..., questions=...)`。决策请求没有默认自动重试。

## 依赖方向

```text
apps/api -> jev_router -> provider/tool protocols
apps/web -> apps/api HTTP contract
 evals -> jev_router public interfaces
 tests -> modules under test
```

核心包避免依赖 API 框架、数据库实现和具体模型 SDK。外部依赖通过小型 adapter 注入，便于离线测试。

## 测试层次

- 单元测试：状态转换、策略阈值边界、工具输入校验、预算耗尽。
- 集成测试：使用 stub HTTP client 验证 Jev request/response 映射和失败处理，不要求真实 API key。
- API 测试：请求 schema、错误状态码、确认流程及 trace 输出。
- Eval：使用固定、版本化用例记录正确动作、允许动作集合和必要确认；分别统计路由一致率、任务完成率、升级率及延迟。

对概率策略至少覆盖阈值等于边界、字段缺失、无效概率和候选工具不可用等情况。真实服务 smoke test 应独立、显式启用，避免普通测试产生费用或副作用。

## 代码约定

- Python 输入和输出使用明确类型；外部 JSON 在边界做 schema 校验，避免在核心逻辑传播裸 `dict[str, Any]`。
- 时间统一使用带时区的 UTC 时间；持续时间使用毫秒或 `timedelta`，字段单位明确。
- 异步 I/O 保持异步调用链一致；客户端设置连接和总超时。
- 对外错误转成稳定、可审计的应用错误；日志包含 task/step 标识，不记录凭证。
- 阈值、预算和模型配置集中管理，并在启动时验证范围。

## 提交前检查

项目配置建立后，至少运行格式化/静态检查、单元测试和相关集成测试。增加或调整策略时同步更新 eval 用例或说明原因。任何失败都应在变更说明中明确记录。
