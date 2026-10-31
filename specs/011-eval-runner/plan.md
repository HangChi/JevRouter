# 实施计划：评测执行循环（Runner）与 LLM 基线

## 设计决策

### 1. LLM 适配器位于核心包内，与 Jev 适配器相邻

`jev_router/clients/llm.py` 与 `clients/jev.py` 同构：冻结的配置在构造时校验、提供 `from_env`、带稳定 `category` 的错误分类，以及在可注入的 `httpx` 传输层之上的单个异步方法。provider 形态采用 Anthropic Messages API（`POST /v1/messages`、`x-api-key` + `anthropic-version`），这让依赖清单保持在 httpx，并让基座 URL 成为换成其他网关时唯一需要改动的东西。

核心包内仍然不含任何自行调用 LLM 的 agent 逻辑；该适配器存在，是为了让 API 的委托处理器与评测基线共用一个经过测试的客户端。

### 2. 基线路由层属于评测基础设施，而非产品路由层

`evals/llm_router.py` 基于同一份路由状态，构造出与 `jev_router.Router` 相同的候选集合（已注册工具加三种控制动作），并要求返回严格的 JSON 对象 `{"action": ..., "reason": ...}`。它返回 `LLMRouteDecision`——动作、原因、模型、延迟、Token——并且刻意不携带任何概率：LLM 基线没有概率，对比表也不能假装它有。

解析采取防御性策略，因为不能保证 provider 一定遵守：先把整段文本当作 JSON 尝试，再提取第一个括号配平的 JSON 对象，最后将动作对照候选集合进行校验。每条失败路径都抛出 `LLMRouterError`，由执行循环（Runner）转换为错误结果。

### 3. 用例是数据，在边界处校验

`EvalCase` 是严格的 pydantic 模型（`extra="forbid"`）：`id`、`goal`、`expected_action`、`allowed_actions`、`requires_confirmation`，以及可选的 `context` 和 `notes`。加载器读取版本化外层结构 `{"version": 1, "cases": [...]}`，拒绝未知版本，并强制执行 schema 无法表达的跨字段规则：id 唯一、列表非空、`expected_action ∈ allowed_actions`，以及动作名去除首尾空白。

已提交的 `cases.json` 包含 53 个用例，覆盖全部五个工具和三种控制动作，其中 `requires_confirmation` 恰好在 `write`/`external` 风险工具上为 true——这与执行循环（Runner）在执行期执行的规则相同，因此该指标衡量的是策略引擎能否自行得出这一结论。

### 4. 执行循环（Runner）是对注入式路由层的纯编排

`EvalRunner` 接收一个 Jev `Router`（或用于构建它的各个部件）、一个可选的基线 `LLMRouter`、一个 `ToolRegistry` 和一个 `PolicyEngine`。对每个用例，它构建与执行循环（Runner）相同的路由状态（`goal`、`step`、`context`、`history`、`last_result`），路由一次，评估策略，并按模式记录一个 `CaseOutcome`。延迟是围绕路由调用的墙钟时间；Token 来自 `RouteDecision`（Jev）或 `LLMRouteDecision`（基线）。

路由层抛出的异常会被捕获并记录为错误结果，因此单个坏用例无法中止整个运行——这与 trace 接收端秉持同样的“失败可见”理念。

`succeeded` 刻意比“动作可接受”更严格：它还要求 `confirmation_requested == requires_confirmation`。这正是阈值需要据以校准的信号。

### 5. 指标是纯函数

`metrics.summarize(outcomes)` 按模式返回 `ModeMetrics`，并返回一个 `ComparisonMetrics`，其中包含在两个路由层都产出动作的那些用例上的一致率。延迟百分位采用最近秩方法（在模块中有说明）；Token 报告均值和总量。空输入得到全零指标。

### 6. API 委托变为可选，而非新增的强制项

`Settings` 新增 `llm_model: str | None` 与 `llm: LLMClientConfig | None`，二者均为 `None`，除非设置了 `LLM_API_KEY`（此时 `LLM_MODEL` 变为必填）。`TaskService` 接受一个可注入的 `llm_client`；一旦完成配置，它就构建一个 `_LLMDelegate`，向模型索取待办步骤所需的推理/回答文本，执行循环（Runner）将其记录为 `delegate_to_llm` 步骤的结果。未配置的部署完全保留第 7 阶段的失败关闭行为：运行以 `failed` 停止，并给出文档中记载的诊断信息。

## 文件布局

```text
jev_router/clients/llm.py     # LLMClientConfig, LLMClient, LLMCompletion, error taxonomy
jev_router/router.py          # + input_tokens/output_tokens on RouteDecision
evals/__init__.py
evals/__main__.py             # python -m evals
evals/cases.py                # EvalCase, load_cases, CaseFileError
evals/cases.json              # 50 versioned cases
evals/registry.py             # deterministic eval registry (same five tools)
evals/llm_router.py           # LLMRouter, LLMRouteDecision, LLMRouterError
evals/runner.py               # EvalRunner, CaseOutcome, EvalReport
evals/metrics.py              # ModeMetrics, ComparisonMetrics, summarize
evals/cli.py                  # argparse CLI
tests/test_llm_client.py
tests/test_llm_router.py
tests/test_eval_cases.py
tests/test_eval_runner.py
tests/test_eval_metrics.py
```

## 测试策略

- 客户端与基线路由层：使用 `httpx.MockTransport` 替身，不联网、不需要凭据、不产生计费请求——与仓库中其他所有测试遵循同一规则。
- 执行循环（Runner）与指标：使用进程内的假路由层，实现相同的调用形态，从而确定性地覆盖策略评估、错误捕获与聚合。
- `cases.json` 由一个测试来校验，因此已提交的文件不会偏离加载器的规则。
- `tests/test_router.py` 新增 Token 用量映射的测试。

## 风险

- **提示词漂移**：基线看到的是手工构建的提示词，所以“同口径”指的是相同的输入，而非相同的编码方式。接受此风险；报告会记录所使用的模型 id。
- **Anthropic 专属形态**：换用其他 provider 意味着换一个客户端，而不是改配置。在 MVP 阶段接受此风险；适配器边界正是发生这次替换的地方。
- **延迟噪声**：在共享机器上单次运行的墙钟时间存在噪声。在 MVP 阶段接受此风险；报告保留每个用例的原始延迟，以便后续阶段可以执行重复运行。
