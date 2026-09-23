# JevRouter

让 LLM 理解和拆解任务，让 Jev 在有限动作中做带概率的路由决策，再由显式策略控制执行。

> 核心包与 API 层已完成 Jev client、工具注册表、Router、Policy Engine、任务状态与预算、Verifier、受限 Runner、trace 持久化和 HTTP 边界九个阶段；Web trace dashboard 与 eval 尚未实现。

## 项目结构

```text
.
├── apps/
│   ├── api/                 # FastAPI 入口、HTTP 路由、配置、SQLite 存储与服务装配
│   └── web/                 # Next.js 仪表盘
├── docs/                    # 架构、开发和安全说明
├── evals/                   # 固定评测用例、运行器和指标
├── jev_router/              # 与 Web/API 框架无关的 Python Agent 核心
│   ├── clients/             # Jev 与 LLM 服务适配器
│   └── tools/               # 工具协议和独立工具实现
└── tests/                   # 单元、集成和 API 测试
```

Python 核心负责状态、路由、策略、执行循环和验证；API 层负责输入校验、配置与依赖装配；Web 层负责交互和 trace 展示。任何模型输出都只是输入，不直接授予执行权限。

## 核心流程

```text
用户目标 -> 任务规范化 -> Jev 路由/风险判断 -> Policy Engine
                                                ├─ 执行工具
                                                ├─ 请求确认
                                                └─ 委托 LLM
执行结果 -> Jev 验证 -> 完成或进入下一步
```

初始工具范围：`web_search`（可先用 mock）、`knowledge_search`、`calculator`、`write_file`、`send_mock_email`。`ask_user`、`delegate_to_llm` 和 `finish` 是控制动作，不是普通工具。

## 关键约束

- Jev 返回 typed decision 和概率；确定性规则、权限检查及副作用仍由应用代码执行。
- 高风险或外部副作用动作必须经过 Policy Engine；确认状态不能被普通路由结果绕过。
- Agent loop 必须有步数和模型调用预算上限，并对失败、低置信度和不可用服务定义明确行为。
- 记录足以重放和评估的 trace，同时避免保存不必要的密钥或敏感内容。
- API 密钥只由服务端读取，不进入浏览器代码、API 响应或日志。
- 阈值是待验证的 MVP 配置，不是 TypeSafe 官方推荐值；变更应通过评测集校准。

## 配置

将本地凭证放在未提交的 `.env` 文件中，并以 `.env.example` 记录变量名称及非敏感说明。服务启动时应对必需配置做校验；不要把真实凭证写进示例文件。

## 开发顺序

已完成：Jev client、工具协议与 registry、Policy Engine、router、任务状态与预算、verifier、受限 runner、trace 持久化、`apps/api` 的 HTTP 边界。

尚未实现：Web trace dashboard、eval 与对比指标。`apps/web/`、`evals/` 仍为空目录。保持核心逻辑可在不启动 Web 的情况下测试。

## 文档

- [架构与模块边界](docs/architecture.md)
- [开发与验证约定](docs/development.md)
- [安全与策略边界](docs/security.md)
- [原始产品设计草案](doc.md)

## 状态

`jev_router/` 已实现并可离线测试：Jev client（`clients/jev.py`）、五个工具与注册表、Router、Policy Engine、不可变任务状态与执行预算、Verifier，以及把它们接成有界循环的 Runner。`apps/api/` 提供 SQLite trace 持久化和 FastAPI HTTP 边界（提交任务、确认待办、提供输入、查询 trace）。`uv run pytest` 现有 133 项测试全部通过，ruff 与 strict mypy 干净；测试使用 httpx mock transport、TestClient 和临时数据库文件，不需要真实凭证。

TypeSafe API 的请求/响应 schema 已在第一阶段依据官方文档确认，仅覆盖 `POST /v1/systemone` 与 `noul`、`choice`、`score` 三种 typed question。若供应商调整接口，应以官方文档为准重新核对，不应从示例推断为稳定契约。

后续按开发顺序推进：Web trace dashboard、eval 与对比指标。`apps/web/`、`evals/` 目前为空目录。
