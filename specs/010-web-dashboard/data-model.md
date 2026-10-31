# 数据模型：Web trace 看板

## 传输类型

`src/lib/types.ts` 手工镜像 `apps/api/schemas.py` 的响应模型。它是一份副本，而不是生成的客户端：API 是事实来源，当彼处某个字段变化时，这份镜像必须同步更新。可选性与 API 一致——API 可能省略的字段在这里为 `| null`，因为存储对从未记录过的概率会返回 `NULL`。

| 类型 | 字段 |
| --- | --- |
| `TaskSummary` | `task_id`, `goal`, `status`, `step` |
| `TaskView` | `TaskSummary` + `diagnostic`, `pending_confirmation`, `pending_input` |
| `PendingConfirmationView` | `action`, `arguments`, `step` |
| `PendingInputView` | `question`, `step` |
| `TraceView` | `step`, `action`, `policy_outcome`, `policy_reason`, `executed`, `result`, `route_confidence`, `route_risk`, `requires_confirmation`, `needs_reasoning`, `confirmed`, `arguments`, `completion_probability`, `quality_score`, `state_snapshot`, `duration_ms` |
| `TaskListResponse` | `tasks: TaskSummary[]` |
| `TraceListResponse` | `task_id`, `traces: TraceView[]` |

`arguments`、`result` 与 `state_snapshot` 是形状未知的 JSON，因此它们被标注为 `unknown` 并通过一个 JSON 查看器渲染，而不是套用固定的模型。`TraceView` 不携带 `task_id`；任务 id 来自包裹它的响应。

## 状态

两套词汇，与第 9 阶段完全相同：

- 实时：`running`、`awaiting_confirmation`、`awaiting_input`。
- 终态：`completed`、`needs_user_input`、`needs_confirmation`、`rejected`、`budget_exhausted`、`failed`。

`statusTone()` 把每一个映射到五种呈现色调之一：`live`、`blocked`、`good`、`bad` 与 `neutral`。`blocked` 同时涵盖实时的阻塞状态，以及因需要人工而结束的终态；`neutral` 用于既不算好也不算坏的控制结果。任何无法识别的值都映射为 `bad`，而不是被渲染得像是一切正常。状态从不只靠颜色承载——徽章会在其圆点旁把传输过来的字符串完整写出。

## 阈值（仅供展示）

`src/lib/thresholds.ts` 镜像 `jev_router/policy.py` 中的 MVP 阈值：

| 常量 | 值 | 用于 |
| --- | --- | --- |
| `ROUTE_CONFIDENCE_THRESHOLD` | `0.75` | `route_confidence` 上的计量条标记 |
| `CONFIRMATION_THRESHOLD` | `0.75` | `requires_confirmation` 上的计量条标记 |
| `REASONING_THRESHOLD` | `0.70` | `needs_reasoning` 上的计量条标记 |
| `RISK_THRESHOLD` | `2.5` | 用于 `route_risk` 的比较值 |
| `COMPLETION_THRESHOLD` | `0.75` | `completion_probability` 上的计量条标记 |

这些常量只用于绘制标记。看板报告的决定来自 API 的 `policy_outcome`；如果这里的某个阈值与核心包产生偏差，标记就是错的，但所报告的结果仍然正确。它们被放在一个带有这条警告的模块中，这样一旦发生偏差就只有一处需要修。

## 评分刻度

`ScoreAnswer.score` 是一个核心包不予归一化的有限浮点数（`jev_router/clients/jev.py` 只检查有限性）。因此抵达看板的两个评分都以原始数字展示，旁边标注其阈值：

- `route_risk` —— 按路由层提交的五个风险等级评分，因此从 0 开始的索引跨越 `0`–`4`，而 `2.5` 这个阈值落在「有意义但可逆」与「外部或有后果」之间。
- `quality_score` —— 按验证器的四级图例评分，因此从 0 开始的索引跨越 `0`–`3`。

`riskLevel()` 与 `qualityLevel()` 在假定这种从 0 开始的索引刻度的前提下，把评分转换为等级条所用的等级索引。该条带用刻度本身作为标注（`scale 0–4`、`scale 0–3`），而不是用等级编号，这样这一假定是被明说的，而不是被断言的。任何评分都不会被绘制为 0–1 的概率条。

## 视图模型

`src/lib/viewModel.ts` 持有作用于传输类型的纯函数，不含 React，也不做 I/O，因此可以直接做单元测试：

- `statusTone(status)` → 色调键；`isLiveStatus(status)` → 是否应继续轮询。
- `policyBranch(trace)` → 一个步骤走了哪条分支：`executed`、`denied`、`approved_failed`、`rejected`、`delegated`、`asked`、`finished`、`not_executed`、`unknown`。由 `policy_outcome`、`executed` 与 `confirmed` 推导；未知的结果产出 `unknown`，而不是猜测。`approved_failed` 正是原始字段使其可见的那种用例：确认已被批准，而工具依然没有运行。
- `probabilityMeters(trace)` → 0–1 的路由计量条，含值、阈值、方向以及是否越过阈值。
- `completionMeter(trace)` → 完成概率的计量条，对于从未被验证的步骤则为 `null`。
- `scoreReadouts(trace)` → `route_risk` 与 `quality_score`，含其阈值、等级索引与等级数。
- `verificationReadout(trace)` → 完成概率与质量评分，当步骤没有验证结果时为 `null`。
- `decisionChain(traces)` → 按步骤顺序每个步骤一个节点，携带动作、结果色调与分支。
- `outcomeTone`、`outcomeLabel`、`branchLabel` → 策略结果与分支的呈现方式。
- `formatDuration(ms)`、`formatProbability(value)`、`formatScore(value)`。

## 步骤计数

用来描述一次运行的两个计数并不是同一个数字。`TaskView.step`
是状态的步骤计数器，API 只有在运行结束后才会记录它；
`traces.length` 是看板实际持有记录的步骤数，
只要某个步骤以 `reject`、`ask_user` 或 `finish` 结束而没有推进状态，
后者就会更大。

列表展示 API 的计数，且只在运行处于终态时展示——实时句柄
报告的是 `0`，那会被读成「没有执行任何步骤」。详情页则统计它
自己渲染的步骤数，并标注为「已记录」。两个数字都不是编造的，
也不会被当作另一个来呈现。

## 视觉编码

颜色是在形式确定之后才选的，而且调色板是经过验证而非凭眼估的。
看板自我遵守的规则：

- **计量条**承载相对于某个上限的单一比值。填充在信号位于其区间内时为强调色相，
  一旦越过阈值进入策略引擎会采取行动的那一侧，则为警示色相；
  未填充的轨道是同一色阶中更浅的一级，因此状态能贯穿整条读出。
  阈值是一条实心细刻度线，其值印在计量条旁边，
  而数值本身始终被印出——
  标记永远不是读出数字的唯一途径。
- **等级条**使用有序的单色相色阶（蓝色，由浅到深），因为
  这些等级是有序的而非名义的。两个色阶都通过有序性检查：
  亮度单调、级间间隔可见，且浅端相对背景的对比度
  超过 2:1。
- **状态颜色**专用于状态，并且始终与传输过来的
  状态字符串配对，因此没有任何信息只靠色相承载。调色板的 `warning` 与
  `serious` 两级在浅色背景上按设计低于 3:1；`serious` 干脆不使用，
  而文字标签就是 `warning` 的缓解手段。
- **文字使用文字令牌。** 数值、标签与说明文字使用墨色令牌；
  颜色存在于它们旁边的标记中。
- **暗色模式是另选的，不是翻转的。** 两个模式都从同一批色阶中
  取用各自的级别，并针对各自的背景来挑选。
- 没有双轴，名义类别上不使用数值色阶，没有虚线网格线，也不在
  每条标记上印数字。

## API 客户端

`src/lib/api.ts` 与 `API_UPSTREAM_URL`（默认 `http://127.0.0.1:8000`）通信，且仅在服务端运行。每个函数都接受一个可选的 fetch 实现，以便测试对其打桩；生产环境使用全局 fetch。失败带有类型：`ApiError` 携带 `4xx`/`5xx` 的上游状态与消息，而 `ApiUnavailableError` 在连接本身失败时携带上游 URL。这一区分很重要，因为 `404` 意味着「没有这个任务」，而连接失败意味着「看板指错了地方」。

## 路由

| 路由 | 渲染内容 |
| --- | --- |
| `/` | 任务列表，最新在前，外加提交表单 |
| `/tasks/[taskId]` | 任务头部、待处理提示、决策链条、步骤卡片 |

## 配置

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `API_UPSTREAM_URL` | `http://127.0.0.1:8000` | `apps/api` 服务器的基础 URL |

Web 应用不读取其他任何配置，也不持有任何凭据。`apps/web/` 中的 `.env.example` 记录了这一个变量。
