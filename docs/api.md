# HTTP API 参考

默认地址 `http://127.0.0.1:8000`。所有请求与响应都是 JSON；成功路径不返回包裹层，错误统一是 `{"detail": "..."}`。

运行中的服务自带 OpenAPI 文档：`http://127.0.0.1:8000/docs`。这份文档与它手写对应，解释的是「为什么这样设计」，而字段清单以 `/docs` 为准。

## 鉴权

设置了 `JEV_API_TOKEN` 时，所有端点（包括 `GET /policy`）都要求：

```
Authorization: Bearer <token>
```

缺失或错误返回 `401`，并带 `WWW-Authenticate: Bearer`。未设置该变量时不鉴权——这是本地开发的默认，生产必须设置，见 [配置参考](configuration.md#安全)。

## 状态码约定

| 码 | 含义 |
| --- | --- |
| `200` / `201` / `202` / `204` | 成功。提交任务是 `202`，因为运行在后台开始，响应时尚未执行 |
| `401` | 配置了 token 但未提供或提供错误 |
| `404` | 任务 id 或评测 run id 不存在 |
| `409` | 当前状态不允许这个操作。确认摘要不符、任务已不在等待、重复回应，都是这一类 |
| `422` | 请求体过不了 schema。`extra="forbid"`，多余字段也会被拒 |

`404` 与 `409` 的区别值得注意：`404` 是「不认识这个东西」，`409` 是「认识，但你现在做这件事没有意义」。仪表盘据此给出不同提示——前者说明 API 重启过，后者说明页面上的信息已经过期。

## 任务状态

任务状态有两套词汇，不要混用。

**存活状态**（由内存里的运行句柄承载）：

| 值 | 含义 |
| --- | --- |
| `running` | 正在跑 |
| `awaiting_confirmation` | 停在待确认，等 `POST /tasks/{id}/confirm` |
| `awaiting_input` | 停在待输入，等 `POST /tasks/{id}/input` |

**终态**（落库到 `tasks` 表）：

| 值 | 含义 |
| --- | --- |
| `completed` | 验证通过，结束 |
| `needs_confirmation` | 需要确认但没拿到批准（含超时） |
| `needs_user_input` | 需要用户输入但没提供 |
| `rejected` | 策略拒绝，例如动作未注册 |
| `budget_exhausted` | 步数或模型调用预算耗尽 |
| `failed` | 出了错，`diagnostic` 里说明原因 |

重要：**运行列表是 API 进程内的注册表，不是数据库查询。** API 重启后列表从空开始，旧 task id 返回 `404`，但 `traces.db` 里的历史记录不受影响。

## 动作名

路由层的候选由「注册的工具 + 三个控制动作」组成：

- 工具：`calculator`、`knowledge_search`、`web_search`、`write_file`、`send_mock_email`
- 控制动作：`ask_user`、`delegate_to_llm`、`finish`

控制动作不是工具，不能被无条件执行；它们对应策略引擎的固定分支。`web_search` 与 `knowledge_search` 需要调用方注入文档，因此不在 API 的默认注册表里——默认只有 `calculator`、`write_file`、`send_mock_email`。

## 端点

### `POST /tasks`

提交一个目标，立即返回（`202`），运行在后台开始。

```json
{ "goal": "计算 (12 + 8) * 3", "context": { "精度": "保留两位小数" } }
```

`goal` 必填，1–2000 字符，不能全是空白。`context` 可选，必须是 JSON 对象。

```json
{ "task_id": "9f2c…", "status": "running" }
```

### `GET /tasks`

最近的运行，最新在前。

查询参数 `limit`：默认 50，必须 ≥ 1。

```json
{ "tasks": [ { "task_id": "9f2c…", "goal": "…", "status": "completed", "step": 1 } ] }
```

### `GET /tasks/{task_id}`

单个任务视图，含待办信息。

```json
{
  "task_id": "9f2c…",
  "goal": "把这句话写进 demo/hello.txt：…",
  "status": "awaiting_confirmation",
  "step": 0,
  "diagnostic": null,
  "pending_confirmation": {
    "action": "write_file",
    "arguments": { "path": "demo/hello.txt", "content": "…" },
    "step": 0,
    "digest": "3f9a1c7b02d4e851",
    "expires_at": "2026-10-31T15:05:12.884193+00:00"
  },
  "pending_input": null
}
```

`pending_confirmation.arguments` 是**合成之后、即将执行的那份参数**，不是动作名。批准的就是它。

### `GET /tasks/{task_id}/traces`

已完成的步骤。被人工阻塞的那一步尚未完成，因此不会出现在这里——待办信息由任务视图的 `pending_*` 给出。

```json
{
  "task_id": "9f2c…",
  "traces": [
    {
      "step": 1,
      "action": "calculator",
      "policy_outcome": "execute",
      "policy_reason": "已注册动作落在当前阈值允许的范围内。",
      "executed": true,
      "result": { "value": 60.0 },
      "route_confidence": 0.98,
      "route_risk": 0.12,
      "requires_confirmation": 0.05,
      "needs_reasoning": 0.08,
      "confirmed": null,
      "arguments": { "expression": "(12 + 8) * 3" },
      "completion_probability": 0.96,
      "quality_score": 3.4,
      "state_snapshot": { "goal": "…", "step": 0, "history": [] },
      "duration_ms": 812
    }
  ]
}
```

`route_*`、`requires_confirmation`、`needs_reasoning` 是模型返回的原始信号，`policy_outcome` 是策略引擎基于它们（与工具风险等级）给出的结论。两者放在一起，才能解释「为什么这一步被拦下」。

### `POST /tasks/{task_id}/confirm`

回应一次待确认。成功返回 `204`。

```json
{ "approved": true, "digest": "3f9a1c7b02d4e851" }
```

`digest` 必填。它来自 `pending_confirmation.digest`，把批准钉在「哪个任务、哪个动作、哪份参数」上：

- 摘要不符 → `409`，任务仍停在待确认。参数被重新合成后，旧批准不会自动生效。
- 任务已经不在等待（过期、已被回应、或运行已结束）→ `409`。
- 超过 `JEV_CONFIRMATION_TTL_SECONDS`（默认 900 秒）→ 按未批准处理，运行以 `needs_confirmation` 结束。

不批准也是回答：`{"approved": false}` 会让运行以 `needs_confirmation` 结束，且不产生副作用。

### `POST /tasks/{task_id}/input`

回答一次追问。成功返回 `204`。

```json
{ "answer": "写进 demo/note.txt" }
```

`answer` 必填，1–4000 字符。当前不在等待输入时返回 `409`。

### `POST /evals`

记录一次评测运行，由 `evals` CLI 投递。成功返回 `201`。

请求体是 [报告信封](development.md#评测) 里的 `data` 字段：`run_id`、`mode`、`created_at`、`outcomes`、`metrics`。

```json
{ "run_id": "b73af4cd…", "case_count": 53 }
```

API 只校验形状，不重算指标——报告的 rates 是随数据一起写出的，重算会让两份算术有漂移空间。`mode` 与 `outcomes` 的一致性也在校验范围内：`compare` 必须每个用例两个路由都有记录。

### `GET /evals`

已记录的运行，最新在前。`limit` 默认 20。

```json
{ "runs": [ { "run_id": "b73af4cd…", "mode": "compare", "created_at": "2026-10-31T14:15:22+00:00", "case_count": 53 } ] }
```

### `GET /evals/{run_id}`

单次运行的完整记录：`metrics` 与按 `(case_id, mode)` 排序的逐用例 `outcomes`。

每条 outcome 除了动作与命中情况，还带 `confidence`、`risk`、`requires_confirmation_probability`、`needs_reasoning_probability`、`tool_risk` 五个原始信号。它们是 [阈值校准](calibration.md) 的输入——没有这些字段的报告无法离线重放。

### `GET /policy`

当前生效的策略。不调用 provider，不花钱，可作为连通性检查。

```json
{
  "thresholds": {
    "confirmation": 0.75,
    "risk": 2.5,
    "reasoning": 0.7,
    "confidence": 0.75,
    "completion": 0.75
  },
  "tools": [
    { "name": "calculator", "risk": "read", "description": "…", "requires_confirmation": false },
    { "name": "write_file", "risk": "write", "description": "…", "requires_confirmation": true }
  ],
  "confirmation_ttl_seconds": 900,
  "confirmation_binding": "task + action + arguments"
}
```

这里返回的是 API 进程中真正生效的值，不是文档里的示例值。仪表盘的 `/policy` 页据此渲染。

## 一次完整走查

```sh
# 1. 提交
TASK=$(curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"goal": "把 hello 写进 demo/hello.txt"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["task_id"])')

# 2. 轮询到等待确认
curl -s http://127.0.0.1:8000/tasks/$TASK | python3 -m json.tool

# 3. 取出 digest 并批准
DIGEST=$(curl -s http://127.0.0.1:8000/tasks/$TASK \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["pending_confirmation"]["digest"])')
curl -s -X POST http://127.0.0.1:8000/tasks/$TASK/confirm \
  -H 'content-type: application/json' \
  -d "{\"approved\": true, \"digest\": \"$DIGEST\"}"

# 4. 看终态与 trace
curl -s http://127.0.0.1:8000/tasks/$TASK | python3 -m json.tool
curl -s http://127.0.0.1:8000/tasks/$TASK/traces | python3 -m json.tool
```

注意第 2 步与第 3 步之间运行是停在原地的：确认是阻塞式的，运行会一直等，直到批准、拒绝或超时。
