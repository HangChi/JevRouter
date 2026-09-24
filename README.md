# JevRouter

让 LLM 理解和拆解任务，让 Jev 在有限动作中做带概率的路由决策，再由显式策略控制执行。

> 十三个阶段全部完成：Jev client、LLM client、工具注册表、Router、Policy Engine、任务状态与预算、Verifier、受限 Runner、trace 持久化、HTTP 边界、Web trace 仪表盘、Eval Runner 与 LLM 基线、eval 结果的持久化与对比仪表盘，以及 LLM 参数合成。

## 项目结构

```text
.
├── apps/
│   ├── api/                 # FastAPI 入口、HTTP 路由、配置、SQLite 存储与服务装配
│   └── web/                 # Next.js 仪表盘
├── docs/                    # 架构、开发和安全说明
├── evals/                   # 固定评测用例、LLM 基线、运行器和指标
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

已完成：Jev client、LLM client、工具协议与 registry、Policy Engine、router、任务状态与预算、verifier、受限 runner、trace 持久化、`apps/api` 的 HTTP 边界、`apps/web` 的 trace 仪表盘、`evals/` 的固定用例集、LLM 基线路由、运行器、指标和 CLI、eval 结果的持久化（`POST/GET /evals`）与对比仪表盘（`/evals`、`/evals/{run_id}`），以及 LLM 参数合成（`LLMArgumentResolver`）。保持核心逻辑可在不启动 Web 的情况下测试。

## 运行评测

```sh
uv run python -m evals --mode compare --json-out evals-report.json
```

`--mode` 可选 `jev`、`llm`、`compare`；凭证从环境变量读取（`JEV_API_KEY`/`JEV_MODEL`、`LLM_API_KEY`/`LLM_MODEL`），缺任何一个都会在跑用例之前失败。加 `--api http://127.0.0.1:8000` 会把报告投递给运行中的 API，落入 `eval_runs` / `eval_case_results` 两张表，仪表盘的 `/evals` 页即可阅读。退出码：0 干净，1 有用例出错，2 配置或用例文件问题，3 报告未能投递。评测是显式动作：测试套件只使用 stub，不产生真实 provider 调用。

## 文档

- [架构与模块边界](docs/architecture.md)
- [开发与验证约定](docs/development.md)
- [安全与策略边界](docs/security.md)
- [原始产品设计草案](doc.md)

## 状态

`jev_router/` 已实现并可离线测试：Jev client（`clients/jev.py`）、LLM client（`clients/llm.py`）、五个工具与注册表、Router、Policy Engine、不可变任务状态与执行预算、Verifier，以及把它们接成有界循环的 Runner。`RouteDecision` 携带 provider 返回的 token 用量，供对比指标使用。`apps/api/` 提供 SQLite trace 持久化和 FastAPI HTTP 边界（提交任务、确认待办、提供输入、查询 trace）；配置了 LLM（`LLM_API_KEY` + `LLM_MODEL`）才装配 `delegate_to_llm` 委托和工具参数合成，否则保持 fail closed——工具以自己的 schema 拒绝空参数。`Tool` 协议暴露 `input_model`，提示词从工具真正校验的那个模型派生，模型输出仍由工具校验。`apps/web/` 是 Next.js trace 仪表盘：运行列表、每步的 Jev 信号/策略结果/执行结果/延迟，以及待确认与待输入的人工应答；所有 API 调用都发生在服务端，浏览器拿不到凭证。`evals/` 用 50 条版本化用例重放同一套 Router/PolicyEngine，并用候选集一致的 LLM 基线对比，产出一致率、匹配率、升级/确认率、延迟与 token 指标；报告可落库并通过 `/evals` 页阅读。`uv run pytest` 现有 250 项测试全部通过，ruff 与 strict mypy 干净；测试使用 httpx mock transport、TestClient 和临时数据库文件，不需要真实凭证。Web 层另有 `tsc --noEmit`、eslint、vitest 和 `next build`。

TypeSafe API 的请求/响应 schema 已在第一阶段依据官方文档确认，仅覆盖 `POST /v1/systemone` 与 `noul`、`choice`、`score` 三种 typed question；LLM 适配器覆盖 Anthropic Messages API 的 `POST /v1/messages`。若供应商调整接口，应以官方文档为准重新核对，不应从示例推断为稳定契约。

