# 数据模型：评测执行循环（Runner）与 LLM 基线

## `EvalCase` (`evals/cases.py`)

严格的冻结 pydantic 模型。表示一条路由预期。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `str` | kebab-case，文件内唯一，最长 64 |
| `goal` | `str` | 用户目标，1–2000 个字符 |
| `expected_action` | `str` | 第一步被认为正确的动作 |
| `allowed_actions` | `tuple[str, ...]` | 非空、无重复、必须包含 `expected_action` |
| `requires_confirmation` | `bool` | 策略引擎是否应在行动前请求确认 |
| `context` | `dict \| None` | 可选的、传给路由状态的任务上下文 |
| `notes` | `str \| None` | 该用例为何有此预期的原因 |

文件格式为 `{"version": 1, "cases": [...]}`。`load_cases` 会拒绝未知版本、格式错误的条目、重复的 id 和空列表；某个用例若被静默丢弃，将使所有上报的比率发生变化。

`requires_confirmation` 恰好在 `write_file` 和 `send_mock_email` 上为 true，与执行循环（Runner）在执行期强制执行的 `write`/`external` 风险规则保持一致。有一个测试会针对已提交的文件断言这一点。

## `RouteDecision` 新增项 (`jev_router/router.py`)

```text
input_tokens: int | None = None
output_tokens: int | None = None
```

由 `DecisionResponse.usage` 填充。是可选的增量字段：运行路径中没有任何代码读取它们，而对比指标需要它们。缺失时取 `None` 而非 `0`，因为“未上报用量”和“零 Token”是两件不同的事实。

## `LLMCompletion` / `LLMRouteDecision`

`LLMCompletion` (`jev_router/clients/llm.py`)：`text`、`model`、`input_tokens`、`output_tokens`。

`LLMRouteDecision` (`evals/llm_router.py`)：`action`、`reason`、`model`、`latency_ms`、`input_tokens`、`output_tokens`。不含概率——基线没有概率，对比也不能凭空编造。

## `CaseOutcome` (`evals/runner.py`)

每个（用例，路由层）对应一行。`mode` 为 `"jev"` 或 `"llm"`，因此一次 compare 运行会为一个用例存下两行，聚合时按 `case_id` 将它们配对。

| 字段 | 含义 |
| --- | --- |
| `action` | 所选动作；路由层出错时为 `None` |
| `matched_expected` / `matched_allowed` | 等于 `expected_action` / 位于 `allowed_actions` 之中 |
| `succeeded` | `matched_allowed` **并且**策略的确认判定与 `requires_confirmation` 相符 |
| `policy_outcome` | 策略引擎的判定结果；基线为 `None` |
| `escalated` | 判定结果属于 `{ask_confirmation, delegate_to_llm, ask_user}`；基线为 `None` |
| `confirmation_requested` | 判定结果为 `ask_confirmation`；基线为 `None` |
| `latency_ms` | 围绕路由调用的墙钟时间，即使失败也会测量 |
| `input_tokens` / `output_tokens` | provider 上报的用量；调用失败时为 `None` |
| `error` | 带类别标记的消息，或 `None` |

`finish` 属于完成，`reject` 属于失败，因此两者都不计为升级。

## `ModeMetrics` / `ComparisonMetrics` (`evals/metrics.py`)

`ModeMetrics` 携带计数与派生比率（`expected_match_rate`、`allowed_match_rate`、`success_rate`、`error_rate`、`escalation_rate`）。基线模式下策略相关字段为 `None`。`latency` 是 `LatencyStats(mean_ms, p50_ms, p95_ms, max_ms)`，采用最近秩百分位；`input_tokens`/`output_tokens` 是 `TokenStats(mean, total)`，当没有任何用例上报用量时为 `None`。

`ComparisonMetrics` 增加 `jev`、`llm`、`agreement_count`、`compared_count`、`disagreement_case_ids` 以及派生出的 `agreement_rate`。除非两种模式各自至少回答了一个用例，否则该比率为 `None`，因为“0%”和“从未对比过”是两种不同的陈述。一致性是在**两个**路由层都产出了动作的那些用例上衡量的。

## `EvalReport` 与传输外层结构

`EvalReport` = `run_id`、`mode`、`created_at`（UTC ISO-8601）、`outcomes`、`metrics`。

`evals/report.py` 将其序列化为 `{"version": 1, "data": {...}}`，各比率是直接写出而非派生计算，因此已存储的报告在不依赖本次构建的算术逻辑时仍可解读。该 `data` 对象就是第 12 阶段 `POST /evals` 所接受的内容。

## 存储（第 12 阶段）

```text
eval_runs           run_id, mode, created_at, case_count, metrics payload
eval_case_results   run_id, case_id, mode, outcome payload
```

两个 payload 列都使用存储层已有的 `{"version": 1, "data": ...}` 外层结构与 `_encode`/`_decode` 配对；`SCHEMA_VERSION` 以增量方式升到 2。
