# 开发与验证约定

## 项目状态

Jev client（`jev_router.clients.jev`）、LLM client（`jev_router.clients.llm`）、工具协议与注册表、Router、Policy Engine、任务状态与执行预算、Verifier、受限 Runner、trace 持久化、API HTTP 边界、Web trace 仪表盘、eval 运行器，以及 eval 结果的持久化与对比仪表盘均已完成。Jev client 仅覆盖文档确认的 `POST /v1/systemone` 以及 `noul`、`choice`、`score` 三种 typed question；LLM client 仅覆盖 Anthropic Messages API 的 `POST /v1/messages`。

## 供应商契约（实测，非推断）

第一次真实 eval（`jev-latest`，50 例）纠正了两处 phase 1 依据文档写下的假设，两者都由离线测试放过、由真实响应抓出：

- `score` 答案的 `legend` 是索引字典 `{"0": "No meaningful side effects", ...}`，`probabilities` 也按同样索引键控，而提交的 criteria 是标签文本。客户端在边界归一化成「有序标签列表 + 按标签键控的概率」，消费者只看一种形状；标签键控的旧形状仍然接受。`tests/test_jev_client.py` 用一份真实抓包的响应做夹具，把这个契约钉住。
- 概率按两位小数四舍五入，8 个候选的合法分布总和可以漂到 1 ± 0.04。原先 1e-3 的容差把舍入噪声当成坏响应——真实运行 50 例里就挂了 1 例。容差改为 0.05，并附理由。`ResponseValidationError` 现在带上「哪个检查失败」，但不带响应体（`docs/security.md` 要求原始响应体不进错误文本）。

LLM client 的 `api_style` 选择 wire format：`messages`（Anthropic，默认）或 `chat_completions`（OpenAI 兼容网关，base URL 需自带版本段，如 `https://api.stepfun.com/step_plan/v1`）。两者产出同一个 `LLMCompletion`，消费者不关心部署用哪种。模型名由调用方显式提供，模型发现不属于已实现范围。项目使用 `pyproject.toml` 和 `uv.lock` 管理依赖。

reasoning 模型有两个联动限制，用 StepFun `step-5-preview` 实测确认：

- **`LLM_MAX_TOKENS` 太小会返回空 completion**。默认 1024 会被思考过程吃光，模型还没产出内容就结束，`LLMCompletion.text` 是空串，委托和参数合成随之失败。这不是解析问题——把预算提到 8192 后同样的用例立刻返回合法 JSON。委托与 resolver 的错误信息因此直接点名这个原因。
- **超时是另一个瓶颈**。放开预算后单个用例要 7～30 秒，默认 30s 超时开始切掉慢用例。评测这类模型时应同时调大 `LLM_MAX_TOKENS` 和 `LLM_TIMEOUT_SECONDS`；生产上则要权衡——委托和参数合成本来只该产生很短输出，大预算主要是评测基线所需。

## 安装与检查

```sh
uv sync --all-groups
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest
```

Web 层（`apps/web/`）用自己的工具链：

```sh
cd apps/web
npm install
npx tsc --noEmit
npm run test      # vitest，视图模型与 API 客户端
npm run lint
npm run build
```

测试使用 HTTPX mock transport，不访问网络、不需要真实凭证，也不产生 billable requests。存储测试使用临时数据库文件。

## 工具层

`jev_router.tools` 提供可信应用代码配置的 `ToolRegistry` 和五个离线 MVP 工具：calculator、knowledge_search、web_search mock、write_file、send_mock_email mock。工具通过同步 `execute(input)` 接口返回 `ToolResult` 并声明 `read`、`write` 或 `external` 风险；该注册表只负责白名单注册、查找和调用，不包含路由或策略授权。搜索数据由调用方注入，邮件只生成模拟结果，均不访问网络。`WriteFileTool` 必须配置根目录，默认拒绝覆盖。

## Router

`jev_router.Router` 基于调用方提供的任务状态、模型标识和 `ToolRegistry`，一次性请求下一动作、风险、确认需求及推理需求，并返回 `RouteDecision`。动作候选由注册工具和 `ask_user`、`delegate_to_llm`、`finish` 组成。Router 仅提供建议，不授权、不执行工具；本地决策由 Policy Engine 完成。

## Task State and Budget

`jev_router.TaskState` stores immutable goal, context, completed-step history, and the latest result. `advance()` returns a new snapshot and does not mutate caller-owned JSON-compatible inputs. `ExecutionBudget` tracks finite step and model-call limits; each consume method returns a new budget and raises `ValueError` when exhausted. These types do not run an agent loop or perform I/O; the future Runner will own orchestration and budget-consumption points.

## Policy Engine

`jev_router.PolicyEngine` 将 `RouteDecision` 映射为显式控制结果，不执行工具。MVP 初始阈值为 `requires_confirmation > 0.75` 或 `risk >= 2.5` 时请求确认；否则 `needs_reasoning > 0.70` 或动作置信度 `< 0.75` 时委托 LLM；其余已注册工具动作才返回 `execute`。`ask_user`、`delegate_to_llm`、`finish` 是对应控制分支，未注册动作拒绝。阈值是项目初值而非服务商推荐，应由 eval 校准。`execute` 不是执行调用；确认结果仍需调用方获取明确的用户批准。

调用方通过 `JevClientConfig.from_env()` 构造配置，并将模型名传给 `JevClient.systemone(model=..., state=..., questions=...)`。决策请求没有默认自动重试。

## Verifier

`jev_router.Verifier` 接收注入的 `JevClient` 和显式模型名，对已完成的 `TaskState` 发起一次 `systemone` 请求，同时提出 `task_complete`（noul）和 `result_quality`（score，四级图例 Not useful → Fully sufficient）两个问题，返回不可变的 `VerificationDecision`，包含 `completion_probability`、`quality_score`、`quality_confidence`、`quality_legend` 和 `model`。`NoulAnswer` 只提供概率，没有独立 confidence 字段，因此完成度没有单独的置信度。

请求 state 由 `TaskState` 的 goal、step、最近 action、`last_result`、context 和 history 组成。由于状态快照使用 `MappingProxyType` 和 `tuple`，而 `json.dumps` 无法序列化 `mappingproxy`，verifier 会先把快照转成纯 JSON 结构，否则会在 client 预检处变成 `RequestValidationError`。没有已完成步骤或 `last_result` 为 `None` 时，在发起请求前抛 `ValueError`。

verifier 只做评估：不设完成阈值、不修改状态、不执行工具、不循环，也不代替 Runner 决定结束或继续路由。

## LLM Client

`jev_router/clients/llm.py` 是与 `clients/jev.py` 对等的 LLM 适配器：冻结的 `LLMClientConfig`（key、base URL、超时、max tokens、API 版本）在构造时校验并提供 `from_env`，`LLMClient.complete(model=..., system=..., prompt=...)` 通过可注入的 httpx transport 发一次 Anthropic Messages API 请求，返回 `LLMCompletion`（text、model、input/output tokens）。错误分类与 Jev client 一致（`configuration`/`request_validation`/`transport`/`http`/`response_decoding`/`response_validation`），调用方按 `category` 处理，不解析供应商错误体。

核心包不自行调用 LLM：适配器存在的意义是让 API 的委托分支、参数合成和 eval 的基线路由共用同一个经过测试的客户端。`RouteDecision` 带有可选的 `input_tokens`/`output_tokens`，来自响应的 `usage`，因为对比指标需要它；缺失时为 `None` 而不是 0。

## Runner

`jev_router.Runner` 把 Router、PolicyEngine 和 Verifier 接成一个有界循环，并在内部用同一个 `ToolRegistry` 装配三者——这样执行前的注册复检不会因为调用方传入不同的 registry 实例而被绕过。`run(goal)` 返回不可变的 `RunResult`，含终止状态 `RunStatus`、最终 `TaskState`、剩余预算、`StepTrace` 序列和诊断信息。

一次迭代消耗 1 个 step 和 1 次 route 模型调用；execute 路径再加 1 次 verify 调用，delegate 路径再加 1 次。循环顶部同时检查两个计数器再消费，避免"先吃掉一个 step 才报告耗尽"。构造时要求 `max_model_calls >= 2 * max_steps`，否则一次可完成的迭代也会被误报成 `budget_exhausted`。

完成阈值由 Runner 持有（默认 0.75，与 Policy Engine 的 MVP 阈值一致），验证不通过就带着前进后的 state 重新路由。若同一个未变化的 state 第二次被判为未完成，直接以 `failed` 停止并留下诊断，而不是把同样的 payload 反复发给 provider 直到预算耗尽。

四个协作者通过 Protocol 注入，缺省全部 fail closed：`ActionInputResolver`（缺省 `{}`，由工具自身 schema 拒绝）、`ConfirmationHandler`（缺省 `needs_confirmation`）、`UserInputHandler`（缺省 `needs_user_input`）、`DelegateHandler`（缺省 `failed`）。`ActionInputResolver` 是参数合成的接缝——`RouteDecision` 只给动作名不给参数，而参数合成属于 LLM 职责；第十三阶段用 `LLMArgumentResolver` 填上了这个接缝。

确认发生在参数合成**之后**：handler 收到的是即将执行的那份参数，而不是只有一个动作名。`tool.risk` 为 `write` 或 `external` 时，即使策略结论是 `execute` 也强制确认——这一条是 Policy Engine 阶段明确推迟到 Runner 的欠账，只信 Jev 概率会让 mock email 和 write_file 在低概率下被自动执行。

provider 报错、工具拒绝输入、resolver 返回非 Mapping、`TaskState.advance` 拒绝结果，统统收敛为 `failed` 加诊断，不会有异常逃出 `run()`。`TraceSink.emit` 抛出的异常不会中断运行，因为 trace 已经记录在 `RunResult.traces` 里，丢失的只是实时投递。

## Trace 持久化

`apps/api/storage.py` 的 `TraceStore` 只消费 Runner 已经产出的不可变记录，不给核心循环增加任何行为；`jev_router` 里没有任何数据库代码。三张表对应三个概念：`tasks`（一行一个 run，含终止状态、步数、诊断和 final state）、`agent_steps`（一行一条 `StepTrace`）、`evaluations`（一行一次验证，按 `(task_id, step)` 关联，不重复塞进 step 行）。

写入有两条路径，共用一个 upsert：`record(RunResult)` 在一个事务里写终态 task 行和全部 trace；`sink()` 返回的 `TraceSink` 在首次发射时upsert 一个 `running` 标记的 task 行，随后每步落库——进程被 kill 时仍留下可读 trace。两者对同一个 `(task_id, step)` 幂等，所以 sink 之后接 `record()` 只会把状态改成终态，不会产生重复行。

版本有两层且都不自动迁移：`PRAGMA user_version` 记录 schema 版本，比当前构建更新的库直接拒绝打开；每个 JSON 列都包成 `{"version": 1, "data": ...}`，读到的版本不明或根本不是版本化信封就抛 `StorageError`。静默误读会污染 trace 记录，所以拒绝是默认行为。

`_encode` 在值无法序列化时退回 `_degrade`：只把出问题的叶子替换成 `{"__unserializable__": ...}`，非有限浮点同样处理，其余内容保留。工具是在输出被接受之前运行的，所以 trace 里完全可能带着 `TaskState.advance` 已经拒绝过的值；为一个坏输出丢掉整条 run 是不可接受的。

`redact=` 回调在编码前作用于 result、arguments 和 state_snapshot，这是 `docs/security.md` 要求在持久化用户目标和工具输入/输出前准备的钩子；保留期限与删除策略仍未定义。凭证保证是结构性的——store 只看得见 `RunResult`/`StepTrace`，永远拿不到 `JevClientConfig`，测试用一个 sentinel key 跑完整 run 后断言数据库文件里不出现这些字节。

连接在 `__init__` 建立，`close()` 或上下文管理器关闭。写入同步且短促，与同步 `TraceSink` 匹配；store 不是线程安全的，应由单个事件循环驱动。连接以 `check_same_thread=False` 建立，因为创建 store 的线程不一定是事件循环所在的线程，而所有访问仍由同一个 loop 串行化。

## API 层

`apps/api/` 分四个模块：`config.py`（启动时校验的冻结 `Settings`）、`schemas.py`（严格请求/响应模型和存活状态常量）、`service.py`（`TaskService` 运行注册表）、`app.py`（app factory、路由和错误映射）。

run 以后台协程执行，请求从不阻塞在 run 上。确认和用户输入通过 future 解决：handler 在 service 上注册一个 `asyncio.Future` 并 await，后续的 `POST /tasks/{id}/confirm` 或 `/input` 再 resolve 它。Runner 本身没有改动——它只是 await 了一个恰好在于等人的 handler。这样做而不是"停下来带批准重启"，是因为重启会重复执行之前步骤已产生的副作用。

存活状态（`running`/`awaiting_confirmation`/`awaiting_input`）与终态 `RunStatus` 是两套词汇：前者由内存中的 handle 承载，后者由 `record()` 写进 `tasks` 行。被人类阻塞的那一步尚未完成，因此 Runner 还没有发射它的 trace；待办信息由 task 视图的 `pending_confirmation`/`pending_input` 给出，而不是塞进 trace 列表。

路由全部声明为 `async def`：FastAPI 会把同步 handler 丢进线程池，那里没有 running loop，`submit()` 里的 `create_task` 会直接失败。

错误映射：未知 task id → `404`；在不该确认/输入时调用 → `409`；body 过不了严格 schema → `422`；`limit < 1` → `400`。`record()` 失败不会篡改 run 的真实终态，只往 diagnostic 里追记一句，因为逐步 trace 已经由 sink 落库。

`default_registry` 只注册 calculator、write_file 和 send_mock_email；两个搜索工具需要调用方注入文档，不放进默认集合。store 只在 app 自己创建时才由 lifespan 关闭，注入的 store 归调用方所有。

eval 结果走同一套存储约定：`eval_runs`（一行一个 run，metrics 载荷）+ `eval_case_results`（一行一条用例结果，按 `(run_id, case_id, mode)` 主键），schema 版本随加法升级到 2，JSON 列沿用同一版本信封，重复记录同一 run id 只替换不追加。`POST /evals` 校验严格 schema、mode 与 outcomes 的一致性（compare 必须每个用例两个路由都有），以及 rates 的取值范围；`GET /evals` 按创建时间倒序分页，`GET /evals/{run_id}` 返回 metrics 和按 `(case_id, mode)` 排序的用例行。未知 run → `404`，`limit < 1` → `400`，body 不过 schema → `422`。API 只校验形状，不重算指标：报告的 rates 是随数据一起写出的，重算会让两份算术有漂移空间。

LLM 协作者是可选装配：`Settings` 的 `llm`/`llm_model` 要么同时配置（`LLM_API_KEY` + `LLM_MODEL`），要么同时缺省；只设其一在启动时报错。配置了才构造 `LLMDelegate` 和 `LLMArgumentResolver`（同在 `apps/api/llm.py`，共用一个 client 和 model）——前者把 LLM 生成的推理文本作为 `delegate_to_llm` 步骤的结果交给 Runner 记录，后者为即将执行的工具合成参数。一个配置驱动两者：能推理但不能参数化的 agent 没有用处。

没有配置时保持第七阶段原始的 fail closed 行为：委托请求让 run 以 `failed` 停止并留下 "delegation was requested but no handler is configured"，工具调用则解析出空参数、由工具自己的 schema 拒绝。显式注入的 `resolver=` 优先于 LLM 的那一个——它是调用方自己的接缝（测试就用它）。provider 报错被包成带 `category` 的 `ValueError` 抛出，由 service 的兜底 handler 转成 failed run；委托静默返回空、或用空参数执行工具，都比失败更糟。

`Tool` 协议因此多了一个成员 `input_model`：工具 `execute` 真正校验的那个 pydantic 模型。参数合成需要告诉模型该给什么，而唯一诚实的描述就是校验本身用的那份——从 `model_json_schema()` 派生提示词，使提示词不可能广告一个工具会拒绝的字段。模型的输出仍然是不可信输入：resolver 原样返回，工具自己的 schema 依旧是唯一权威。

## Web 层

`apps/web/` 是 Next.js 仪表盘，只读 `apps/api` 的端点（六个任务相关 + 三个 eval 相关）。所有 API 调用都发生在服务端：server component 读，server action 写，浏览器只与 Next.js 服务器同源通信，因此 `apps/api` 不需要 CORS，凭证也不可能到达前端。上游地址来自 `API_UPSTREAM_URL`（默认 `http://127.0.0.1:8000`），这是该层唯一的配置。

`src/lib/types.ts` 是 `apps/api/schemas.py` 的手写镜像，不是生成的客户端：API 是唯一事实来源，字段变更必须同步。`src/lib/thresholds.ts` 是 `jev_router/policy.py` 阈值的展示用副本，只用来画刻度线——仪表盘报告的结论永远是 API 返回的 `policy_outcome`，所以阈值副本即使漂移也不会改变结论，只会让刻度线失真；它们集中在一个模块里，就是为了让这种漂移只有一处可修。

`src/lib/viewModel.ts` 是纯函数层：状态色调、步骤分支、概率表、分数读数、验证读数和决策链都在这里决定，组件只负责排版和着色。三个 `noul` 概率按 0–1 画成带阈值刻度的 meter；`route_risk` 和 `quality_score` 是核心包不做归一化的 provider score，因此只显示原始数值加有序色阶，并标注刻度范围（`scale 0–4`、`scale 0–3`），绝不画成 0–1 概率条。缺失字段渲染成「—」而不是 0：`NULL` 和真实的 `0.0` 是两件事。

实时刷新由 `<LiveRefresh>` 完成：run 处于存活状态时每 2 秒 `router.refresh()` 一次，到达终态后自动停止。待确认和待输入由 server action 应答，`409` 说明 run 在渲染和点击之间已经继续前进，此时把 API 的原话显示出来，而不是假装应答成功。

`/evals` 与 `/evals/[runId]` 是只读页面：eval run 是已结束的记录，不轮询、不起跑。列表页展示最新一次的聚合卡片，详情页一行一个用例并排两个路由的动作、延迟与 token。视图模型对“模式产生不了的指标”直接省略而不是画 0，对路由出错的行显示错误且不计入分歧——否则一致率会被提供方故障拉低。

## Eval

`evals/` 只依赖 `jev_router` 的公开接口（`evals/cli.py` 除外，它是唯一跨层模块，用 `apps.api.schemas` 的模型向运行中的 API 投递报告）。五个模块各司其职：`cases.py`（严格 `EvalCase` 模型与版本化 loader）、`cases.json`（50 条固定用例，覆盖五个工具和三个控制动作）、`registry.py`（带固定 fixture 的五工具注册表，保证可复现且离线）、`llm_router.py`（LLM 基线路由，候选集与 `jev_router.Router` 完全一致，要求严格 JSON 输出）、`runner.py`（逐用例路由一次、过一遍真实 PolicyEngine、产出 `CaseOutcome`）、`metrics.py`（纯聚合）、`report.py`（版本化报告序列化）。

`CaseOutcome.succeeded` 比"动作可接受"更严：还要求策略的确认结论与用例的 `requires_confirmation` 一致——这正是阈值校准需要的信号。`requires_confirmation` 只对 `write`/`external` 风险工具为真，与 Runner 执行时的强制确认同一条规则，因此该指标衡量的是 Policy Engine 能否自己得出这个结论。延迟百分位用最近秩法（50 个样本的 p95 是排序后第 48 个值），token 统计只覆盖有用例回数的场景。

CLI：`uv run python -m evals --mode jev|llm|compare [--limit N] [--json-out PATH]`。凭证全部来自环境变量，缺任何一个都在跑用例之前失败；有用例出错时退出码为 1，配置或用例文件问题为 2，干净运行为 0。评测是显式动作，测试绝不触发真实 provider 调用。

## 依赖方向

```text
apps/api -> jev_router -> provider/tool protocols
apps/web -> apps/api HTTP contract
 evals -> jev_router public interfaces
 evals/cli -> apps/api HTTP contract (投递报告)
 tests -> modules under test
```

`evals/` 的库模块（cases、runner、metrics、llm_router、registry、report）只依赖 `jev_router` 公开接口；`evals/cli.py` 是唯一跨层模块，通过 HTTP 把报告投递给 `apps/api`，不 import 它。

核心包避免依赖 API 框架、数据库实现和具体模型 SDK。外部依赖通过小型 adapter 注入，便于离线测试。

## 测试层次

- 单元测试：状态转换、策略阈值边界、工具输入校验、预算耗尽。
- 集成测试：使用 stub HTTP client 验证 Jev/LLM request/response 映射和失败处理，不要求真实 API key。
- 存储测试：临时 SQLite 文件验证 trace 往返、增量写入、版本化载荷、脱敏与降级。
- API 测试：请求 schema、错误状态码、确认流程、LLM 委托与参数合成装配及 trace 输出，含一次用合成参数真实执行工具的端到端 run。
- Web 测试：vitest 覆盖视图模型与 API 客户端（注入 fetch），加上 `tsc --noEmit` 与 `next build`。
- Eval：使用固定、版本化用例记录正确动作、允许动作集合和必要确认；分别统计路由一致率、任务完成率、升级率及延迟。用例集本身由测试校验，loader 规则与提交的 `cases.json` 不会悄悄漂移。
- 存储与 API：临时 SQLite 文件验证 eval run 往返、重复记录幂等、载荷版本拒绝，以及 version-1 数据库升级后仍可写读；`TestClient` 验证 `POST/GET /evals` 的状态码与 round-trip。
- CLI：stub router 驱动 `main()`，覆盖退出码、报告信封与 `--api` 投递（MockTransport）。

对概率策略至少覆盖阈值等于边界、字段缺失、无效概率和候选工具不可用等情况。真实服务 smoke test 应独立、显式启用，避免普通测试产生费用或副作用。

## 代码约定

- Python 输入和输出使用明确类型；外部 JSON 在边界做 schema 校验，避免在核心逻辑传播裸 `dict[str, Any]`。
- 时间统一使用带时区的 UTC 时间；持续时间使用毫秒或 `timedelta`，字段单位明确。
- 异步 I/O 保持异步调用链一致；客户端设置连接和总超时。
- 对外错误转成稳定、可审计的应用错误；日志包含 task/step 标识，不记录凭证。
- 阈值、预算和模型配置集中管理，并在启动时验证范围。

## 提交前检查

项目配置建立后，至少运行格式化/静态检查、单元测试和相关集成测试。增加或调整策略时同步更新 eval 用例或说明原因。任何失败都应在变更说明中明确记录。
