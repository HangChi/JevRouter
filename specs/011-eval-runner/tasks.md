# 任务：评测执行循环（Runner）与 LLM 基线

## 阶段 1：LLM 适配器

- [x] T001 实现 `jev_router/clients/llm.py`：冻结的 `LLMClientConfig`（密钥、基座 URL、超时、最大 Token 数、API 版本）并提供 `from_env`；在可注入的 httpx 传输层之上实现 `LLMClient.complete(*, model, system, prompt, max_tokens)`；实现 `LLMCompletion`（文本、模型、输入/输出 Token）以及错误分类（`LLMClientError` 带 `category`，另有配置/传输/http/响应几个变体）。
- [x] T002 针对 `httpx.MockTransport` 对客户端做单元测试：请求路径、请求头、请求体形态；文本与用量解析；非 2xx、传输失败、非法 JSON 与缺少 content 的映射；配置对空白密钥、非 HTTPS 基座 URL 和非正超时的拒绝；`from_env` 的默认值。

## 阶段 2：基线路由层与 Token 用量

- [x] T003 实现 `evals/llm_router.py`：从注册表取得候选集合再加上三种控制动作；提示词携带目标/步骤/历史/上一次结果；严格 JSON 解析并支持括号配平提取；候选校验；`LLMRouteDecision`（动作、原因、模型、latency_ms、输入/输出 Token）以及 `LLMRouterError`。
- [x] T004 用桩客户端对基线路由层做单元测试：能从裸 JSON 和围栏 JSON 中解析出动作；未知动作、格式错误的 JSON 和缺失键会抛出异常；延迟与 Token 被记录；提示词包含目标以及每一个候选动作。
- [x] T005 为 `RouteDecision` 增加可选的 `input_tokens`/`output_tokens`，由 provider 响应中的用量字段填充，并在 `tests/test_router.py` 中覆盖该映射。

## 阶段 3：用例

- [x] T006 实现 `evals/cases.py`：严格 `EvalCase` 模型，以及读取版本化外层结构的 `load_cases`，拒绝未知版本、重复 id、空列表、空白/未去除首尾空白的动作，以及期望动作不在允许集合内的情况。
- [x] T007 编写 `evals/cases.json`，包含 50 个用例：覆盖每个已注册工具与全部三种控制动作，`requires_confirmation` 恰好在 `write_file`/`send_mock_email` 上为 true，kebab-case id 稳定，并设置若干包含多个动作的允许集合，使允许匹配与期望匹配产生差异。
- [x] T008 针对已提交文件测试加载器（数量、唯一性、期望动作是否在允许集合内、确认标记），并针对手工构造的非法文件测试（未知版本、重复 id、空列表、期望动作不在允许集合内）。

## 阶段 4：执行循环（Runner）与指标

- [x] T009 实现 `evals/registry.py`：确定性的五工具注册表（带固定测试数据的搜索工具，`write_file` 以调用方提供的临时目录为根），使一次运行可复现且离线。
- [x] T010 实现 `evals/runner.py`：在注入式路由层之上的 `EvalRunner`，路由状态构建方式与执行循环（Runner）一致；逐用例的 `CaseOutcome`（动作、匹配标记、策略判定结果、升级、确认、延迟、Token、错误、succeeded）以及 `EvalReport`（运行 id、模式、created_at、结果、指标）；路由层异常会变成错误结果。
- [x] T011 实现 `evals/metrics.py`：`summarize` 产出按模式的计数与比率、升级/确认计数、延迟均值/p50/p95/最大值、Token 均值/总量，以及两个路由层都作答的用例上的跨模式一致率；空输入返回全零指标。
- [x] T012 用假路由层对执行循环（Runner）做单元测试：两种模式与 compare、策略判定结果驱动升级/确认、抛异常的路由层被记录为错误结果、确认不匹配时 `succeeded` 为 false。
- [x] T013 对指标做单元测试：精确的比率算术、百分位取值位置、仅对配对用例计算一致性，以及空输入。

## 阶段 5：命令行与 API 委托

- [x] T014 实现 `evals/cli.py` 与 `evals/__main__.py`：`--cases`、`--mode jev|llm|compare`、`--jev-model`、`--llm-model`、`--json-out`、`--limit`；凭据从环境解析，缺失时在任何用例运行之前失败；输出 stdout 摘要；任何用例出错时退出码非零。
- [x] T015 为 `apps/api` 增加可选的 LLM 委托：从 `LLM_MODEL`/`LLM_API_KEY` 得到 `Settings.llm_model`/`Settings.llm`（默认均不存在）、`TaskService` 上可注入的 `llm_client`、一个向模型索取待办步骤推理文本的 `_LLMDelegate`，以及测试：未配置的服务在委托时仍然失败关闭，而已配置的服务通过桩客户端完成委托。

## 阶段 6：文档与检查

- [x] T016 更新 `README.md`、`docs/development.md`、`docs/architecture.md`、`docs/security.md` 和 `.env.example`，以覆盖 LLM 适配器、评测包、命令行与委托接线；把 `evals` 加入 mypy 调用。
- [x] T017 编写本规格目录下的 `data-model.md` 与 `quickstart.md`，然后运行 ruff、对 `jev_router apps evals` 运行严格 mypy，以及完整的 pytest 套件。
- [x] T018 对真实应用进行验证：用桩实现的 Jev 客户端与桩实现的 LLM 客户端在 uvicorn 下启动 `apps.api`，通过 curl 驱动一次委托运行，并在进程内用假路由层运行评测命令行以确认报告形态。

## 依赖关系

T001 先于 T003/T015。T005 独立。T006–T008 先于 T010。T009–T011 先于 T012/T013。T014 需要 T010–T013。T016–T018 在实施之后进行。

## 完成标准

所有任务只有在实施与验证之后才会被勾选。本阶段不改动任何阈值取值，且 `evals/{cases,runner,metrics,llm_router,registry}.py` 不从 `apps/` 导入任何内容。
