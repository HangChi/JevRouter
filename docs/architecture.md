# 架构与模块边界

## 目标

JevRouter 使用 TypeSafe Jev 对有限候选动作进行结构化判断，并把判断结果、概率与任务状态交给本地策略代码。LLM 负责自然语言理解、复杂任务拆解和内容生成；常规业务流程、状态变更、预算控制和副作用由应用代码负责。

## 建议模块

| 路径 | 职责 |
| --- | --- |
| `jev_router/state.py` | 不可变任务快照、步骤历史与有限执行预算 |
| `jev_router/clients/jev.py` | Jev HTTP/API 适配，隔离供应商 schema |
| `jev_router/clients/llm.py` | LLM 规范化、推理委托和内容生成适配（Anthropic Messages API） |
| `jev_router/router.py` | 构建路由判断输入并解析 typed decision |
| `jev_router/policy.py` | 将置信度、风险与确认要求映射到允许的控制动作 |
| `jev_router/runner.py` | 有预算上限的 route/execute/verify 状态循环 |
| `jev_router/verifier.py` | 判断结果是否满足目标，并给出完成概率与结果质量评估 |
| `jev_router/tools/base.py` | 工具输入、输出、风险等级、输入模型和执行协议 |
| `jev_router/tools/` | calculator、search、knowledge、file 和 mock email 实现 |
| `apps/api/` | HTTP 边界、配置、SQLite trace 存储、LLM 协作者和核心服务装配 |
| `apps/web/` | 发起任务、确认待办、查看运行 trace、对比评测、查看当前策略 |
| `evals/` | 固定数据集、LLM 基线路由、运行器、指标计算、报告投递与阈值校准 |

核心任务状态与执行预算是不可变快照。状态推进会记录每一个已完成的动作/结果；预算消耗递减有限的步骤额度或模型调用额度，并在额度耗尽时拒绝。后续的执行循环（Runner）负责决定何时消耗这些预算以及如何停止。持久化与序列化不在状态契约的范围之内。

核心包不应依赖 FastAPI 或前端框架。服务适配器负责将供应商响应转换为内部模型，避免供应商字段渗入 policy 和 runner。

模型输出（包括参数合成产物）是不可信输入：`Tool.input_model` 既是提示词的来源，也是 `execute` 的校验依据，两者因此不可能漂移；工具的参数约束（路径沙箱、AST 白名单、长度上限）对合成参数与手写参数一视同仁。

`apps/web/` 只依赖 `apps/api` 的 HTTP 契约，并且所有 API 调用都发生在 Next.js 服务端：server component 负责读，server action 负责写，浏览器只与 Next.js 服务器同源通信。这样 `apps/api` 不需要为浏览器开 CORS，凭证也不可能进入前端代码或响应体。实时刷新用轮询而不是流式，因为 API 没有流式端点；轮询在 run 到达终态时停止。

## 决策边界

1. 校验并规范化用户目标及可用工具集合。
2. Router 请求一次 Jev 评估，涵盖候选动作、风险、确认需求和复杂推理需求；候选工具只来自可信注册配置，模型名从服务能力发现或配置中获取，不永久硬编码。
3. 策略引擎重新校验被推荐的工具动作当前仍处于注册状态，再套用显式的置信度、风险、确认与推理阈值来选出控制结果。`execute` 不是工具调用；任何必需的显式用户批准都必须由调用方单独获取。
4. Runner 拥有预算消耗点和循环终止权，并在执行前再次复检注册状态，再把已合成的参数交给确认处理器。是否需要确认由策略引擎的结论决定（其中包含「工具声明为 `write`/`external` 就无条件确认」这条下限），Runner 不再重复实现一遍风险等级判断。参数合成属于 LLM 职责，通过注入的 resolver 提供；配置了 LLM（`LLM_API_KEY` + `LLM_MODEL`）时由 `LLMArgumentResolver` 填充该接缝，未配置时工具以自己的 schema 拒绝空参数而 fail closed。`delegate_to_llm` 分支同理。
5. 工具执行器按工具自身 schema 校验输入；对外部或不可逆副作用强制确认。
6. verifier 报告完成概率与结果质量；是否结束或继续循环由 Runner 决定，本阶段只提供评估，不设完成阈值、不改状态、不执行工具。
7. 每一步产生一条 `StepTrace`，包含状态快照、请求/响应摘要、决策概率、策略结果、执行结果与延迟；Runner 在内存中产出，持久化由 `apps/api/storage.py` 负责。
8. eval 用固定用例重放同一套 Router/PolicyEngine，并用候选集完全一致的 LLM 基线路由做对比；它只测量，不改变被测量的对象，也不改阈值。

策略引擎的判定顺序是：控制动作 → 未注册动作拒绝 → **工具风险下限** → 概率阈值。只要工具声明为 `write` 或 `external`，就返回确认，与模型给出的分数无关；其余动作才按 `requires_confirmation`、`risk`、`needs_reasoning`、路由置信度依次判断。四个阈值收在 `PolicyThresholds` 里并可由环境变量覆盖，默认值 `0.75 / 2.5 / 0.70 / 0.75` 是项目初值，不是 TypeSafe 给出的建议，应当用评测来校准。

这条「下限」曾经同时写在策略引擎之外的执行循环里，而评测只读策略结论，于是同一套规则产生了两种说法：评测报告 17 条应确认用例中触发 0 条。规则收敛到一处之后，执行与度量共用同一份判断。

`evals/ --mode calibrate` 是第四个与评测相关的动作：它读一份已记录的报告，在其中的概率信号上重放策略引擎，为候选阈值打分，不接触任何 provider。校准只提出建议，是否写回部署配置由人决定——自动改写阈值等于把安全边界交给一次运行的噪声。

`evals/` 的用例、基线路由和指标都只依赖 `jev_router` 公开接口；LLM 基线与 Jev 看到同一份 goal/history 和同一份候选集，但它不产生概率，因此对比表里它的置信度一栏必须留空而不是填 0。eval 运行是显式的 CLI 动作，测试不会触发真实 provider 调用。

对比仪表盘只读已记录的 run：`GET /evals` 列表 + `GET /evals/{run_id}` 详情，渲染聚合卡片与逐用例对比表。它不重算、不轮询、不起跑——一个 run 是结束了的记录，把“提供方故障”和“两个路由确实存在分歧”区分开是显示层的事：出错的行显示错误，且不计入一致率的分母。

模型提供建议而非授权。`finish`、`ask_user` 和 `delegate_to_llm` 必须作为受控分支处理，不能被当作工具名无条件执行。Policy Engine 只返回控制结果，不调用工具，也不代替用户确认。

## 状态和持久化

核心状态至少应表达 task id、goal、status、step、context、available tools、history、last result 和调用预算。持久化实体从 `tasks`、`agent_steps`、`evaluations` 开始，实现在 `apps/api/storage.py`；SQLite 是 MVP 默认方案。序列化格式分两层版本化——schema 版本走 `PRAGMA user_version`，每个 JSON 载荷自带版本信封——避免未来 schema 变更使旧 trace 无法读取，或更糟地被静默误读。两者都不自动迁移，遇到不认识的版本直接拒绝。

`TaskState` 本身仍不含 task id 和 status：这两项由 Runner 的 `RunResult` 承载，持久化时落到 `tasks` 行。核心包不依赖任何数据库实现。

eval 结果是第二类持久化实体：`eval_runs` 与 `eval_case_results` 从第十二阶段加入，与 trace 共用同一套版本信封和 upsert 惯例，schema 版本随加法递增。eval 报告由 CLI 通过 `POST /evals` 投递，API 校验其形状与 mode/outcome 一致性后原样存储，不重算指标——报告的 rates 随数据一起写出，读取时不需要本构建的算术参与解释。`evals/` 的库模块只依赖 `jev_router` 公开接口；只有 CLI 通过 HTTP 与 API 对话。

## 非目标

MVP 不引入 LangChain/LangGraph、不执行任意 shell 命令、不接真实邮件服务，也不承诺多租户生产级隔离。真实外部集成应单独设计授权、审计、重试和幂等策略。
