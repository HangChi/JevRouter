# JevRouter

一句话定位：

> **让 LLM 负责理解复杂任务，让 Jev 决定 Agent 下一步该做什么。**

TypeSafe 当前 API 很适合这个结构：`POST /v1/systemone` 接受一个共享 `state`，一次请求可以混合多个 `noul`、`choice`、`score` 问题，并返回概率/置信度；模型名称则可以通过 `GET /v1/models` 获取，而不是在代码里永久写死。

------

## 1. 最终架构

我建议第一版做成这样：

```text
                         ┌─────────────────┐
                         │      User       │
                         │  "查一下服务器…" │
                         └────────┬────────┘
                                  │
                                  ▼
                       ┌────────────────────┐
                       │   Task Normalizer  │
                       │      LLM           │
                       │                    │
                       │ user intent        │
                       │ constraints        │
                       │ context            │
                       └─────────┬──────────┘
                                 │
                                 ▼
              ┌─────────────────────────────────┐
              │           Jev Router            │
              │                                 │
              │  Choice → next_tool             │
              │  Score  → risk                  │
              │  Noul   → requires_confirmation │
              │  Noul   → needs_reasoning       │
              └────────────────┬────────────────┘
                               │
                   ┌───────────┼────────────┐
                   │           │            │
                   ▼           ▼            ▼
              confidence     uncertain      risky
                足够高           │            │
                   │             ▼            ▼
                   │          LLM Router   User Confirm
                   │
                   ▼
           ┌────────────────┐
           │ Tool Executor  │
           └───────┬────────┘
                   │
                   ▼
            ┌──────────────┐
            │ Jev Verifier │
            │              │
            │ complete?    │
            │ retry?       │
            │ result risk? │
            └──────┬───────┘
                   │
             ┌─────┴──────┐
             ▼            ▼
          Finished      Next Step
```

关键点是：

**Jev 不做 Planner。**

它做的是：

> 给定当前状态，从有限的下一步动作中做决定。

这和 TypeSafe 对 Jev 的定位很一致：typed decisions、routing、scoring、branching、verification，而不是自由文本生成。([TypeSafe AI](https://typesafe.ai/blog/introducing-system-one-models-and-jev?utm_source=chatgpt.com))

------

# 2. 第一版不要做太多 Tool

MVP 建议只放 5 个：

| Tool               | 类型     | 风险 |
| ------------------ | -------- | ---- |
| `web_search`       | 读取     | 低   |
| `knowledge_search` | 读取     | 低   |
| `calculator`       | 计算     | 低   |
| `write_file`       | 修改     | 中   |
| `send_mock_email`  | 外部操作 | 高   |

外加两个特殊 action：

```text
ask_user
delegate_to_llm
```

所以 Jev 实际选择的是：

```text
web_search
knowledge_search
calculator
write_file
send_mock_email
ask_user
delegate_to_llm
finish
```

这样已经足够展示完整 Agent Router 了。

------

# 3. Jev Router 最核心的一次请求

这是整个项目最重要的设计。

不要连续调用 Jev 四次。

因为 Jev API 本身支持在同一个 `state` 上同时问多个不同类型的问题。

你可以构造这样的状态：

```json
{
  "user_goal": "帮我查一下东京明天天气，然后发邮件告诉 Alice",
  "current_step": 0,
  "completed_actions": [],
  "available_tools": [
    "web_search",
    "knowledge_search",
    "calculator",
    "write_file",
    "send_mock_email"
  ],
  "context": {},
  "last_result": null
}
```

然后一次问 Jev：

```json
{
  "model": "jev-latest",
  "state": {
    "user_goal": "帮我查一下东京明天天气，然后发邮件告诉 Alice",
    "current_step": 0,
    "completed_actions": [],
    "available_tools": [
      "web_search",
      "knowledge_search",
      "calculator",
      "write_file",
      "send_mock_email"
    ]
  },
  "questions": {
    "next_action": {
      "type": "choice",
      "instructions": "Choose the best next action to progress toward the user's goal.",
      "criteria": {
        "web_search": "Search external/current information",
        "knowledge_search": "Search internal knowledge",
        "calculator": "Perform arithmetic",
        "write_file": "Write or modify a file",
        "send_mock_email": "Send an email",
        "ask_user": "More information is required",
        "delegate_to_llm": "The decision requires complex reasoning",
        "finish": "The task is already complete"
      }
    },
    "risk": {
      "type": "score",
      "instructions": "Rate the risk of executing the selected next action.",
      "criteria": [
        "No meaningful side effects",
        "Minor reversible side effects",
        "Meaningful but reversible action",
        "External or consequential action",
        "Potentially destructive or irreversible action"
      ]
    },
    "requires_confirmation": {
      "type": "noul",
      "instructions": "Should the user explicitly confirm before this action is executed?"
    },
    "needs_reasoning": {
      "type": "noul",
      "instructions": "Does choosing the correct next step require deeper multi-step reasoning?"
    }
  }
}
```

这就是 JevRouter 的核心。

官方 schema 里，`choice` 会返回选中的 choice、confidence 以及各选项概率；`score` 会返回 probability-weighted score、confidence 和每个等级的概率；`noul` 则直接返回“yes/true”的概率。

------

# 4. 不要只看 Jev 的最终 Choice

这是你的项目可以比普通 demo 更有意思的地方。

假设：

```json
{
  "next_action": {
    "choice": "web_search",
    "confidence": 0.82,
    "probabilities": {
      "web_search": 0.82,
      "knowledge_search": 0.04,
      "calculator": 0.01,
      "send_mock_email": 0.03,
      "ask_user": 0.04,
      "delegate_to_llm": 0.06
    }
  }
}
```

你的 Router 不应该只是：

```python
execute("web_search")
```

而应该有一个 **Policy Engine**。

```text
Jev = Intelligence
Policy Engine = Control
Tool = Execution
```

这是整个系统最重要的分层。

------

# 5. Policy Engine

第一版我建议这么设计：

```python
if requires_confirmation > 0.75:
    return ASK_CONFIRMATION

if risk_score >= 2.5:
    return ASK_CONFIRMATION

if needs_reasoning > 0.70:
    return DELEGATE_TO_LLM

if route_confidence < 0.75:
    return DELEGATE_TO_LLM

return EXECUTE
```

这些 `0.75 / 2.5 / 0.70` **不是 Jev 官方推荐阈值**，而是我们 MVP 的初始值。

以后通过 eval 数据重新 calibration。

最终应该变成：

```text
Jev probability
      ↓
Policy Thresholds
      ↓
Action
```

而不是：

```text
AI 说干嘛
   ↓
直接干
```

------

# 6. Jev 和 LLM 怎么分工

这个边界非常重要。

| 问题                | Jev  | LLM      |
| ------------------- | ---- | -------- |
| 下一步调用哪个 Tool | ✅    | fallback |
| 是否需要确认        | ✅    |          |
| 风险评分            | ✅    |          |
| 是否完成            | ✅    |          |
| 是否值得重试        | ✅    |          |
| 从 8 个动作里选一个 | ✅    |          |
| 理解复杂自然语言    |      | ✅        |
| 拆复杂任务          |      | ✅        |
| 写邮件              |      | ✅        |
| 写长文本            |      | ✅        |
| 深度推理            |      | ✅        |
| 生成 Tool 参数      |      | ✅        |

所以你可以理解成：

```text
LLM = Think

Jev = Decide

Code = Act
```

这是 JevRouter 最核心的理念。

------

# 7. TaskState

我会把整个 Agent 的状态统一定义成：

```typescript
interface TaskState {
  taskId: string;

  goal: string;

  step: number;

  status:
    | "running"
    | "waiting_confirmation"
    | "completed"
    | "failed";

  context: Record<string, unknown>;

  availableTools: ToolDefinition[];

  history: AgentStep[];

  lastResult?: ToolResult;

  budget: {
    maxSteps: number;
    maxLLMCalls: number;
    maxJevCalls: number;
  };
}
```

每一步：

```typescript
interface AgentStep {
  step: number;

  stateSnapshot: unknown;

  decision: JevDecision;

  policyDecision:
    | "execute"
    | "confirm"
    | "delegate"
    | "finish";

  tool?: string;

  toolInput?: unknown;

  toolOutput?: unknown;

  latencyMs: number;

  timestamp: string;
}
```

一定要保存：

```text
state
→ Jev decision
→ probability
→ policy decision
→ action
→ result
```

这样以后才能做 replay 和 evaluation。

------

# 8. Tool 接口

所有 Tool 统一：

```typescript
interface Tool {
  name: string;

  description: string;

  risk: "read" | "write" | "external";

  execute(input: unknown): Promise<ToolResult>;
}
```

例如：

```typescript
const calculator: Tool = {
  name: "calculator",

  description: "Evaluate mathematical expressions.",

  risk: "read",

  async execute(input) {
    // ...
  }
};
```

Router 根本不关心具体实现。

因此以后添加：

```text
GitHub
Gmail
Slack
Database
Shell
Browser
Calendar
Stripe
```

Router 都不用重新设计。

------

# 9. 第二个 Jev：Verifier

这是我很建议你加的部分。

很多 Agent：

```text
Tool 调用了
↓
默认成功
```

你的系统应该：

```text
Tool Result
     ↓
Jev Verifier
```

state：

```json
{
  "goal": "找到东京明天天气",
  "action": "web_search",
  "result": {
    "temperature": "24°C",
    "weather": "rain"
  }
}
```

问题：

```json
{
  "task_complete": {
    "type": "noul",
    "instructions": "Does the current result satisfy the user goal?"
  },

  "result_quality": {
    "type": "score",
    "instructions": "Rate how well the result satisfies the goal.",
    "criteria": [
      "Not useful",
      "Partially useful",
      "Mostly sufficient",
      "Fully sufficient"
    ]
  }
}
```

然后：

```text
complete > 0.9
       ↓
FINISH

complete < 0.9
       ↓
ROUTER AGAIN
```

这样就形成了真正的 loop：

```text
              ┌───────────┐
              │   State   │
              └─────┬─────┘
                    ↓
              ┌───────────┐
              │ Jev Route │
              └─────┬─────┘
                    ↓
              ┌───────────┐
              │   Tool    │
              └─────┬─────┘
                    ↓
             ┌─────────────┐
             │ Jev Verify  │
             └──────┬──────┘
                    │
               incomplete
                    │
                    └──────────────┐
                                   │
                                   ▼
                                 State
```

TypeSafe 本身也把 verify / score / judge / guardrail 作为 Jev 特别适合的使用模式。([TypeSafe AI](https://typesafe.ai/blog/introducing-system-one-models-and-jev?utm_source=chatgpt.com))

------

# 10. Dashboard 才是这个项目真正“出彩”的地方

后端做好以后，我很建议做一个简单 Web UI。

主页左边：

```text
┌─────────────────────────────┐
│ JevRouter                   │
│                             │
│ 帮我查东京天气，然后写到    │
│ weather.txt                 │
│                             │
│              [Run Agent]    │
└─────────────────────────────┘
```

右侧实时出现：

```text
STEP 1
────────────────────────

Decision

web_search

Confidence
█████████████████░░  89%

Alternatives

web_search        89%
knowledge_search   4%
delegate_llm       3%
ask_user           2%
others             2%

Risk
█░░░░  0.8 / 4

Confirmation
12%

Needs reasoning
8%

Latency
104 ms

Policy
AUTO EXECUTE
```

然后：

```text
STEP 2

Decision
write_file

Confidence
94%

Risk
2.1 / 4

Confirmation
43%

Policy
AUTO EXECUTE
```

这样别人一眼就知道：

> Jev 到底在干什么。

------

# 11. 再做一个非常有价值的功能：LLM vs Jev

Dashboard 放：

```text
Routing Mode

○ Jev
○ LLM
○ Compare
```

Compare：

```text
                    JEV           LLM
─────────────────────────────────────
Decision         web_search     web_search

Latency             112ms        1830ms

Input tokens          423          612

Output tokens          12           97

Route agreed          ✓

Confidence           .94           —
```

跑 100 / 1000 条测试数据后：

```text
Jev vs LLM

Routing agreement          91.4%

Jev avg latency            118 ms
LLM avg latency           1642 ms

Jev escalation rate        7.8%

Human confirmation rate    4.2%

Task success               92.1%
```

这一下就不只是 Demo 了。

它开始变成一个真正的 **Jev benchmark / Agent infrastructure project**。

------

# 12. 数据库

SQLite 第一版完全够。

```text
tasks
────────────────
id
goal
status
created_at
finished_at


agent_steps
────────────────
id
task_id
step
state_json
jev_request_json
jev_response_json
decision
confidence
policy_action
tool
tool_input_json
tool_output_json
latency_ms


evaluations
────────────────
task_id
success
steps
jev_calls
llm_calls
total_latency
human_interventions
```

这样之后可以非常方便地做 dashboard。

------

# 13. 技术栈

我推荐：

```text
Frontend
Next.js
TypeScript
Tailwind
Recharts

Backend
FastAPI
Python

Agent Core
纯 Python
不要第一版上 LangChain

AI
Jev API
+
OpenAI / Anthropic 任意一个作为 fallback

DB
SQLite
↓
之后 PostgreSQL
```

尤其是：

**第一版不要用 LangChain / LangGraph。**

不是因为它们不好，而是你的项目核心正是：

> Router 如何工作。

如果用了大量 Agent Framework，最关键的逻辑反而藏起来了。

你自己写 loop 大概就 100～200 行。

------

# 14. Repo 我会这样组织

```text
jev-router/
│
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   │
│   └── web/
│       └── Next.js
│
├── jev_router/
│   │
│   ├── router.py
│   ├── verifier.py
│   ├── policy.py
│   ├── state.py
│   ├── runner.py
│   │
│   ├── clients/
│   │   ├── jev.py
│   │   └── llm.py
│   │
│   └── tools/
│       ├── base.py
│       ├── calculator.py
│       ├── search.py
│       ├── knowledge.py
│       ├── file.py
│       └── email.py
│
├── evals/
│   ├── cases.json
│   ├── runner.py
│   └── metrics.py
│
├── tests/
│
├── .env.example
├── README.md
└── pyproject.toml
```

------

# 15. 第一版开发顺序

我建议严格控制范围，按这个顺序做：

1. **Jev Client**：封装 `/v1/models` 和 `/v1/systemone`，支持 `noul / choice / score`；不要把具体 Jev model 名硬编码死，因为官方 API 提供 `/v1/models` 来获取当前账号可用模型。
2. **Tool Registry**：先实现 calculator、knowledge search、web/search mock、write file、mock email。
3. **Router**：一次 Jev 请求同时得到 `next_action + risk + confirmation + needs_reasoning`。
4. **Policy Engine**：根据 confidence、risk、confirmation probability 决定 `execute / confirm / delegate`。
5. **Agent Loop**：实现 `state → route → execute → verify → state`，并强制 `max_steps` 防止无限循环。
6. **Verifier**：Tool 执行后让 Jev 判断任务是否完成。
7. **Trace Storage**：所有 Jev request、response、概率、tool result 全保存。
8. **Dashboard**：把每一步 Decision Graph、概率、latency 和 policy 显示出来。
9. **Eval Runner**：准备 50～100 个固定任务，同时跑 Jev Router 与 LLM Router。
10. **Comparison Dashboard**：展示 latency、routing agreement、task success、escalation rate 和调用成本。

这样第一阶段就已经是一个非常完整的 GitHub 项目了。

------

## 最终产品应该长这样

用户输入：

> 找一下 Python 3.15 最近有什么变化，然后把主要变化写进 notes.md。

系统内部：

```text
USER
 │
 ▼
LLM Task Normalizer
 │
 ▼
JEV ROUTER
 │
 ├─ web_search       91%
 ├─ knowledge_search  3%
 ├─ write_file        1%
 ├─ delegate_llm      4%
 └─ ask_user          1%
 │
 │ confidence 91%
 │ risk 0.4
 │ confirm 3%
 ▼
AUTO EXECUTE
 │
 ▼
WEB SEARCH
 │
 ▼
JEV VERIFIER
 │
 │ complete 41%
 ▼
JEV ROUTER
 │
 ├─ write_file       94%
 └─ ...
 │
 ▼
LLM
generate file content
 │
 ▼
WRITE FILE
 │
 ▼
JEV VERIFIER
 │
 │ complete 97%
 ▼
FINISH
```

**这个就是我认为 JevRouter 最合理的 V1。**

而且它有一个很好的演进方向：V1 是 Agent Router，V2 可以加入动态 Tool Registry，V3 加 graph execution，V4 做成类似 **“Jev-native Agent runtime”** 的 SDK：

```python
agent = JevAgent(
    tools=[search, github, email],
    policy=SafePolicy()
)

result = await agent.run(
    "检查项目问题并把严重 bug 通知我"
)
```

到那时候它就已经不只是作品集，而是有可能成为一个真正开源库的东西了。TypeSafe 目前强调的正是“把智能拆成许多细粒度、带概率的 decision，再由代码组合成可靠 workflow”，所以这个方向与 Jev 的模型特性非常匹配。([TypeSafe AI](https://typesafe.ai/blog/introducing-system-one-models-and-jev?utm_source=chatgpt.com))