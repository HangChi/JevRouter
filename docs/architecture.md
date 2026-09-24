# 架构与模块边界

## 目标

JevRouter 使用 TypeSafe Jev 对有限候选动作进行结构化判断，并把判断结果、概率与任务状态交给本地策略代码。LLM 负责自然语言理解、复杂任务拆解和内容生成；常规业务流程、状态变更、预算控制和副作用由应用代码负责。

## 建议模块

| 路径 | 职责 |
| --- | --- |
| `jev_router/state.py` | Immutable task snapshots, step history, and finite execution budgets |
| `jev_router/clients/jev.py` | Jev HTTP/API 适配，隔离供应商 schema |
| `jev_router/clients/llm.py` | LLM 规范化、推理委托和内容生成适配（Anthropic Messages API） |
| `jev_router/router.py` | 构建路由判断输入并解析 typed decision |
| `jev_router/policy.py` | 将置信度、风险与确认要求映射到允许的控制动作 |
| `jev_router/runner.py` | 有预算上限的 route/execute/verify 状态循环 |
| `jev_router/verifier.py` | 判断结果是否满足目标，并给出完成概率与结果质量评估 |
| `jev_router/tools/base.py` | 工具输入、输出、风险等级和执行协议 |
| `jev_router/tools/` | calculator、search、knowledge、file 和 mock email 实现 |
| `apps/api/` | HTTP 边界、配置、SQLite trace 存储和核心服务装配 |
| `apps/web/` | 发起任务、确认待办、查看运行 trace |
| `evals/` | 固定数据集、LLM 基线路由、运行器、指标计算和报告投递 |

Core task state and execution budgets are immutable snapshots. State advancement records each completed action/result; budget consumption decrements a finite step or model-call allowance and rejects exhausted limits. The later Runner owns when to consume these budgets and how to stop. Persistence and serialization are outside the state contract.

核心包不应依赖 FastAPI 或前端框架。服务适配器负责将供应商响应转换为内部模型，避免供应商字段渗入 policy 和 runner。

`apps/web/` 只依赖 `apps/api` 的 HTTP 契约，并且所有 API 调用都发生在 Next.js 服务端：server component 负责读，server action 负责写，浏览器只与 Next.js 服务器同源通信。这样 `apps/api` 不需要为浏览器开 CORS，凭证也不可能进入前端代码或响应体。实时刷新用轮询而不是流式，因为 API 没有流式端点；轮询在 run 到达终态时停止。

## 决策边界

1. 校验并规范化用户目标及可用工具集合。
2. Router 请求一次 Jev 评估，涵盖候选动作、风险、确认需求和复杂推理需求；候选工具只来自可信注册配置，模型名从服务能力发现或配置中获取，不永久硬编码。
3. Policy Engine revalidates that a recommended tool action is currently registered, then applies explicit confidence, risk, confirmation, and reasoning thresholds to select a control outcome. `execute` is not a tool call; any required explicit user approval must be obtained separately by the caller.
4. Runner 拥有预算消耗点和循环终止权，并在执行前再次复检注册状态、强制 `write`/`external` 风险工具的确认，且把确认绑定到已合成的参数上。参数合成属于 LLM 职责，通过注入的 resolver 提供；`delegate_to_llm` 分支同理，只有服务端显式配置了 LLM（`LLM_API_KEY` + `LLM_MODEL`）时才装配委托 handler，否则 fail closed。
5. 工具执行器按工具自身 schema 校验输入；对外部或不可逆副作用强制确认。
6. verifier 报告完成概率与结果质量；是否结束或继续循环由 Runner 决定，本阶段只提供评估，不设完成阈值、不改状态、不执行工具。
7. 每一步产生一条 `StepTrace`，包含状态快照、请求/响应摘要、决策概率、策略结果、执行结果与延迟；Runner 在内存中产出，持久化由 `apps/api/storage.py` 负责。
8. eval 用固定用例重放同一套 Router/PolicyEngine，并用候选集完全一致的 LLM 基线路由做对比；它只测量，不改变被测量的对象，也不改阈值。

MVP Policy Engine thresholds are `requires_confirmation > 0.75`, `risk >= 2.5`, `needs_reasoning > 0.70`, and route confidence `< 0.75`, in that precedence. They are initial project values, not TypeSafe recommendations, and should later be calibrated against evals. Unknown or no-longer-registered actions fail closed with `reject`.

`evals/` 的用例、基线路由和指标都只依赖 `jev_router` 公开接口；LLM 基线与 Jev 看到同一份 goal/history 和同一份候选集，但它不产生概率，因此对比表里它的置信度一栏必须留空而不是填 0。eval 运行是显式的 CLI 动作，测试不会触发真实 provider 调用。

对比仪表盘只读已记录的 run：`GET /evals` 列表 + `GET /evals/{run_id}` 详情，渲染聚合卡片与逐用例对比表。它不重算、不轮询、不起跑——一个 run 是结束了的记录，把“提供方故障”和“两个路由 genuinely 分歧”区分开是显示层的事：出错的行显示错误，且不计入一致率的分母。

模型提供建议而非授权。`finish`、`ask_user` 和 `delegate_to_llm` 必须作为受控分支处理，不能被当作工具名无条件执行。Policy Engine 只返回控制结果，不调用工具，也不代替用户确认。

## 状态和持久化

核心状态至少应表达 task id、goal、status、step、context、available tools、history、last result 和调用预算。持久化实体从 `tasks`、`agent_steps`、`evaluations` 开始，实现在 `apps/api/storage.py`；SQLite 是 MVP 默认方案。序列化格式分两层版本化——schema 版本走 `PRAGMA user_version`，每个 JSON 载荷自带版本信封——避免未来 schema 变更使旧 trace 无法读取，或更糟地被静默误读。两者都不自动迁移，遇到不认识的版本直接拒绝。

`TaskState` 本身仍不含 task id 和 status：这两项由 Runner 的 `RunResult` 承载，持久化时落到 `tasks` 行。核心包不依赖任何数据库实现。

eval 结果是第二类持久化实体：`eval_runs` 与 `eval_case_results` 从第十二阶段加入，与 trace 共用同一套版本信封和 upsert 惯例，schema 版本随加法递增。eval 报告由 CLI 通过 `POST /evals` 投递，API 校验其形状与 mode/outcome 一致性后原样存储，不重算指标——报告的 rates 随数据一起写出，读取时不需要本构建的算术参与解释。`evals/` 的库模块只依赖 `jev_router` 公开接口；只有 CLI 通过 HTTP 与 API 对话。

## 非目标

MVP 不引入 LangChain/LangGraph、不执行任意 shell 命令、不接真实邮件服务，也不承诺多租户生产级隔离。真实外部集成应单独设计授权、审计、重试和幂等策略。
