# 配置参考

所有配置都来自环境变量，没有配置文件、没有命令行覆盖（评测 CLI 的部分参数除外）。服务启动时一次性校验，配错了在接第一个请求之前就失败。

本地开发把这些写进仓库根的 `.env`；`.env` 已被忽略，**不要**把真实凭证写进 `.env.example`。

## 凭证

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JEV_API_KEY` | 无，必填 | Jev 的 API key。缺失时客户端构造即失败 |
| `JEV_MODEL` | 无，必填 | 模型 id。不要硬编码猜测，用你账号可用的那个；文档实测用的是 `jev-latest` |
| `JEV_BASE_URL` | 客户端默认 | Jev 服务地址，一般不用改 |
| `JEV_TIMEOUT_SECONDS` | `30` | 单次决策请求超时 |

`JEV_TIMEOUT_SECONDS` 值得单独说：实测 p95 约 2 秒，但长尾会撞到 30 秒并让整条用例报 `transport` 错误。真实部署建议 60。

## LLM（可选，两项必须成对配置）

不配置时系统保持 fail closed：遇到「委托给 LLM」的分支会以 `failed` 停下并留下诊断，工具参数解析成空、由工具自己的 schema 拒绝。这是设计上要的结果——能推理但不能参数化的 agent 没有用，与其半残地跑，不如明确停下。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 无 | 与 `LLM_MODEL` 必须同时给或同时不给 |
| `LLM_MODEL` | 无 | 同上 |
| `LLM_BASE_URL` | 见 `.env.example` | 走 `chat_completions` 时，base URL 要自带版本段，例如 `https://api.stepfun.com/step_plan/v1` |
| `LLM_API_STYLE` | `messages` | `messages` = Anthropic Messages API；`chat_completions` = OpenAI 兼容网关 |
| `LLM_API_VERSION` | `2023-06-01` | 仅 `messages` 使用，写进 `anthropic-version` 头 |
| `LLM_MAX_TOKENS` | `1024` | 单次 completion 上限 |
| `LLM_TIMEOUT_SECONDS` | `30` | 单次请求超时 |

**推理模型的两个坑**（实测于 `step-5-preview`）：

- `LLM_MAX_TOKENS` 太小时，模型把预算耗在思考上就结束了，`completion.text` 是空串。这不是解析问题，把预算提到 8192 后同样的输入立刻返回合法 JSON。委托与参数合成的错误信息会直接点名这个原因。
- 放开预算后单个用例要 7–30 秒，默认 30 秒超时开始切掉慢用例。评测这类模型时 `LLM_MAX_TOKENS` 与 `LLM_TIMEOUT_SECONDS` 要一起调。

评测 CLI 另有 `--llm-max-tokens` / `--llm-timeout`，用来给基线单独设一份预算，不影响服务端配置。

## 策略阈值

这些值决定「自动执行 / 请人确认 / 交给 LLM」的边界。它们是**项目初值，不是服务商推荐值**，改它应当由评测数据驱动，见 [阈值校准](calibration.md)。

| 变量 | 默认 | 超过/低于会怎样 |
| --- | --- | --- |
| `JEV_CONFIRMATION_THRESHOLD` | `0.75` | 确认概率**高于**它 → 请人确认 |
| `JEV_RISK_THRESHOLD` | `2.5` | 风险分**达到**它 → 请人确认（取值域 `0`–`4`） |
| `JEV_REASONING_THRESHOLD` | `0.70` | 推理需求**高于**它 → 交给 LLM |
| `JEV_ROUTE_CONFIDENCE_THRESHOLD` | `0.75` | 动作置信度**低于**它 → 交给 LLM |
| `JEV_COMPLETION_THRESHOLD` | `0.75` | 验证器完成概率**达到**它 → 结束任务 |

判定顺序是有意的：控制动作 → 未注册拦截 → **工具风险下限** → 上面这些阈值。也就是说，只要工具声明为 `write` 或 `external`，一律要求确认，与模型给出的分数无关；阈值只对 `read` 类工具起作用。

`JEV_COMPLETION_THRESHOLD` 是这五个里唯一**不属于策略引擎**的：它由执行循环持有，决定「验证器说完成到什么程度才收工」。它也不在校准器的搜索网格里——校准器只重放 policy 的四个阈值，因为报告里没有逐用例的完成概率。这意味着它只能靠人工判断，下面的实测是个起点：

一条把文件写好的任务，验证器给的完成概率是 **0.69**（另一次 0.68），质量分 2.2 左右。按默认 0.75 判，它会继续循环、第二次仍然不过、最后被「状态没有变化」规则判成 `failed`——而文件其实写对了。降到 **0.65** 之后同样的场景第 1 步就 `completed`。

**现在的默认是保留 0.75**，不靠降阈值来让任务收尾：低于阈值时运行不再判 `failed`，而是以 `needs_confirmation` 停下交给人，诊断里带着两边分数（例如 `0.71 < 0.75`）。实测一条写文件任务就是这样收尾的——文件内容正确，但验证器只给 0.71，于是把判断权交出来。

0.65 仍然是一个选项，但它要解决的问题变了：不是「让任务能结束」，而是「少被打扰」。代价是「确实没做完」的任务会更早被认成完成，这比多跑两步贵得多，所以默认不选它。

## 确认

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JEV_CONFIRMATION_TTL_SECONDS` | `900` | 待确认的有效期。超时按「没有批准」处理，运行以 `needs_confirmation` 结束 |

一次批准绑定 `task + action + arguments` 的摘要，参数变了旧批准立即失效。这条规则不提供关闭开关。

## 运行与预算

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JEV_MAX_STEPS` | `8` | 单次运行最多几步 |
| `JEV_MAX_MODEL_CALLS` | `16` | 单次运行最多几次模型调用。必须 ≥ `2 × JEV_MAX_STEPS`，因为每步至少一次路由加一次验证 |
| `JEV_DATABASE_PATH` | `traces.db` | SQLite 路径；目录必须已存在 |
| `JEV_WORKSPACE_ROOT` | `./workspace` | `write_file` 的根目录，工具拒绝越出它的路径 |

预算耗尽不是异常，是正常终态：运行会以 `budget_exhausted` 结束并留下诊断。

## 安全

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JEV_API_TOKEN` | 未设置 | 设置后所有端点要求 `Authorization: Bearer <token>`；不设置则不做鉴权，启动时打一条 warning |

不设置是为了本地仪表盘开箱可用。服务的边界约定是「默认只绑回环地址」——用 `--host 127.0.0.1` 启动，或者容器里只映射到 `127.0.0.1`。**一旦要对外提供服务，必须设置它。**

## Web 仪表盘

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `API_UPSTREAM_URL` | `http://127.0.0.1:8000` | 上游 API 地址，末尾斜杠会被去掉 |

仪表盘自身不持有任何 provider 凭证：所有 API 调用都发生在 Next.js 服务端，浏览器只与 Next 服务器同源通信，所以 `apps/api` 不需要开 CORS。

## 校验行为

配置在启动时校验，出错直接拒绝启动而不是带病运行：

- 缺 `JEV_MODEL` → 启动失败。
- 只配了 `LLM_API_KEY` 或只配了 `LLM_MODEL` → 启动失败，提示两项必须成对。
- `JEV_MAX_MODEL_CALLS < 2 × JEV_MAX_STEPS` → 启动失败。
- 阈值超出范围（概率须在 `0`–`1`，风险分须在 `0`–`4`）→ 启动失败。
- 数值变量不是数字 → 启动失败，并点名是哪个变量。

## 默认值 vs 已校准值

仓库里的默认值是保守的初值。本文档记录的那次校准只改动了一个维度（`JEV_ROUTE_CONFIDENCE_THRESHOLD` 0.75 → 0.65），依据与推导过程见 [阈值校准](calibration.md)。部署时把校准结果写进 `.env`，不要改代码里的默认值——默认值要留给「还没跑过评测的人」。
