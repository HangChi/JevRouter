# JevRouter

让 LLM 理解和拆解任务，让 Jev 在有限动作中做带概率的路由决策，再由显式策略控制执行。

> 十三个阶段全部完成：Jev client、LLM client、工具注册表、Router、Policy Engine、任务状态与预算、Verifier、受限 Runner、trace 持久化、HTTP 边界、Web trace 仪表盘、Eval Runner 与 LLM 基线、eval 结果的持久化与对比仪表盘，以及 LLM 参数合成。
>
> 之后又做了一轮加固：把「工具风险必须确认」这条规则从两处实现收敛到策略引擎一处（这是评测里「17 条应确认、实际 0 条」的根因）、阈值改为可配置、确认绑定参数摘要与过期时间、API 支持 Bearer 鉴权，并新增了离线阈值校准器与 `/policy` 策略页。


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

除凭证外，这些变量会影响行为：

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `JEV_CONFIRMATION_THRESHOLD` | `0.75` | 确认概率超过它请求人工批准 |
| `JEV_RISK_THRESHOLD` | `2.5` | 风险分达到它请求人工批准（`0`–`4`） |
| `JEV_REASONING_THRESHOLD` | `0.70` | 推理需求超过它交给 LLM |
| `JEV_ROUTE_CONFIDENCE_THRESHOLD` | `0.75` | 动作置信度低于它交给 LLM |
| `JEV_COMPLETION_THRESHOLD` | `0.75` | 完成概率达到它结束任务 |
| `JEV_CONFIRMATION_TTL_SECONDS` | `900` | 待确认的有效期，过期按未批准处理 |
| `JEV_API_TOKEN` | 未设置 | 设置后所有端点要求 `Authorization: Bearer` |

阈值是项目初值，不是服务商推荐值；改它应当由评测数据驱动，见下一节。


## 开发顺序

已完成：Jev client、LLM client、工具协议与 registry、Policy Engine、router、任务状态与预算、verifier、受限 runner、trace 持久化、`apps/api` 的 HTTP 边界、`apps/web` 的 trace 仪表盘、`evals/` 的固定用例集、LLM 基线路由、运行器、指标和 CLI、eval 结果的持久化（`POST/GET /evals`）与对比仪表盘（`/evals`、`/evals/{run_id}`），以及 LLM 参数合成（`LLMArgumentResolver`）。保持核心逻辑可在不启动 Web 的情况下测试。

## 运行评测

```sh
uv run python -m evals --mode compare --json-out evals-report.json
```

`--mode` 可选 `jev`、`llm`、`compare`、`calibrate`；前三者从环境变量读取凭证（`JEV_API_KEY`/`JEV_MODEL`、`LLM_API_KEY`/`LLM_MODEL`），缺任何一个都会在跑用例之前失败。加 `--api http://127.0.0.1:8000` 会把报告投递给运行中的 API，落入 `eval_runs` / `eval_case_results` 两张表，仪表盘的 `/evals` 页即可阅读。退出码：0 干净，1 有用例出错，2 配置或用例文件问题，3 报告未能投递。评测是显式动作：测试套件只使用 stub，不产生真实 provider 调用。

## 校准阈值

`calibrate` 模式**不调用任何 provider**：它读一份已经跑出来的报告，在记录下来的信号上重放策略引擎。

```sh
# 1) 先跑一次真实评测，报告里会带上每条用例的置信度、风险分、确认概率、推理概率与工具风险等级
uv run python -m evals --mode compare --json-out evals-report.json

# 2) 离线搜一遍阈值网格，看哪一组最划算
uv run python -m evals --mode calibrate --from-report evals-report.json --top 10
```

输出是一张表：每组阈值下自动执行/确认/委托各多少条、有多少个**错误的动作被自动执行**、确认失配多少次。排序优先保证不把错的动作自动执行掉，其次少打扰人，最后才看委托次数；全部打平时偏向自动执行面更小的一侧。最后几行给出推荐值，并且会额外标注两件事——**哪些维度在本批用例上无论怎么调都不改变结果**（改它没有证据），以及**哪些维度取到了搜索范围边沿**（只能读作「网格内最好」）。

### 2026-10-31 的实测结论

53 条用例、`jev-latest` 与 `step-5-preview` 基线的三轮真实运行：

| 阶段 | Jev 期望命中 | 升级率 | 确认 |
| --- | --- | --- | --- |
| 加固前（50 用例旧口径） | 56% | 56% | **0/17** |
| 规则收敛后（53 用例） | 81.1% | 62.3% | 16/17 |
| 改写工具描述后 | 92.5% | 54.7% | 16/17 |
| 校准阈值后（`confidence=0.65`） | 92.5% | **50.9%** | 16/17 |

- **确认从 0/17 变成 16/17**，剩下 1 条是路由器选了 `ask_user` 而不是写工具，属于动作判断问题，不是确认机制问题。
- 命中率从 81.1% 提升到 92.5% 不是调阈值调出来的：10 个错误里有 9 个是 `ask_user` 过度触发，根因是 `knowledge_search` 的描述只讲实现（"injected set of local knowledge documents"）不讲「什么时候该用」，模型只好退回去追问。把描述改成说明能力边界之后，同一批用例直接提升 5 条。
- 阈值校准只带来一处有证据的改动：`confidence` 从 0.75 降到 0.65，让两条判断正确（conf 0.68 / 0.70）的读类动作恢复自动执行，升级 29→27，错误自动执行次数仍为 0。确认/风险/推理三个维度在这批用例上完全不影响结果，因此保持默认——工具会明确提示这一点。
- 顺带发现 `JEV_TIMEOUT_SECONDS` 默认 30 秒偏紧：p95 只有 2 秒，但长尾会撞到 30 秒并让一条用例超时报错。部署时建议 60。


## 容器运行

```sh
docker build -t jevrouter-api .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env \
  -v "$PWD/data:/app/data" jevrouter-api

cd apps/web && docker build -t jevrouter-web \
  --build-arg API_UPSTREAM_URL=http://127.0.0.1:8000 . && \
  docker run --rm -p 127.0.0.1:3000:3000 jevrouter-web
```

镜像不含任何凭证，`--env-file` 负责把它们注入 API 进程；数据库与工作区挂在 `/app/data`，否则容器一删 trace 就没了。


## 文档

- [架构与模块边界](docs/architecture.md)
- [开发与验证约定](docs/development.md)
- [安全与策略边界](docs/security.md)
- [Web 仪表盘手动验证清单](docs/web-manual-checks.md)
- [原始产品设计草案](doc.md)

## 状态

`jev_router/` 已实现并可离线测试：Jev client（`clients/jev.py`）、LLM client（`clients/llm.py`）、五个工具与注册表、Router、Policy Engine、不可变任务状态与执行预算、Verifier，以及把它们接成有界循环的 Runner。策略引擎独占「是否需要确认」这一判断：工具声明为 `write`/`external` 时无条件确认，其余才看概率；阈值经 `PolicyThresholds` 可配置。`RouteDecision` 携带 provider 返回的 token 用量，供对比指标使用。

`apps/api/` 提供 SQLite trace 持久化和 FastAPI HTTP 边界（提交任务、确认待办、提供输入、查询 trace、读取当前策略）；确认必须回传参数摘要，超过 TTL 自动失效；配置了 `JEV_API_TOKEN` 就对所有端点做 Bearer 校验。配置了 LLM（`LLM_API_KEY` + `LLM_MODEL`）才装配 `delegate_to_llm` 委托和工具参数合成，否则保持 fail closed——工具以自己的 schema 拒绝空参数。

`apps/web/` 是 Next.js 仪表盘：运行列表、每步的 Jev 信号/策略结果/执行结果/延迟、待确认与待输入的人工应答，以及 `/evals` 对比页和 `/policy` 策略页；所有 API 调用都发生在服务端，浏览器拿不到凭证。

`evals/` 用 53 条版本化用例重放同一套 Router/PolicyEngine，并用候选集一致的 LLM 基线对比，产出一致率、匹配率、升级/确认率、延迟与 token 指标；报告可落库并通过 `/evals` 页阅读，也可以作为 `calibrate` 模式的输入离线校准阈值。

`uv run pytest` 现有 303 项测试全部通过，ruff 与 strict mypy 干净；测试使用 httpx mock transport、TestClient 和临时数据库文件，不需要真实凭证。Web 层另有 104 项 vitest、`tsc --noEmit`、eslint 和 `next build`，CI 覆盖这两条链路。


TypeSafe API 的请求/响应 schema 已在第一阶段依据官方文档确认，仅覆盖 `POST /v1/systemone` 与 `noul`、`choice`、`score` 三种 typed question；LLM 适配器覆盖两种 wire format（`LLM_API_STYLE`）：Anthropic Messages API 的 `POST /v1/messages` 与 OpenAI 兼容的 `POST /chat/completions`。第一次真实 eval 纠正了两处文档假设（score 答案的索引式 legend、概率舍入导致的分布漂移），实测契约记录在 `docs/development.md`。若供应商调整接口，应以官方文档为准重新核对，不应从示例推断为稳定契约。

