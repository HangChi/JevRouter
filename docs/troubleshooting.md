# 故障排查

按症状索引。每条先给「怎么判断」，再给「为什么」和「怎么办」。

## 启动

### 启动就报 `JEV_MODEL 是必填项`

没读到环境变量。用 `uvicorn` 直接起时 `.env` 不会被自动加载：

```sh
uv run --env-file .env uvicorn apps.api.app:create_app --factory --port 8000
```

容器里则是 `--env-file .env` 传给 `docker run`，不是 `docker build`。

### 启动报 `JEV_MAX_MODEL_CALLS 至少要允许每步一次路由和一次验证`

`max_model_calls` 必须 ≥ `2 × max_steps`。每步至少一次路由加一次验证，配得比这少的话，一个本该能跑完的任务也会被误报成预算耗尽。

### 启动报阈值越界

概率类阈值必须在 `0`–`1`，`JEV_RISK_THRESHOLD` 必须在 `0`–`4`。这类错误在启动时暴露是有意为之：带病运行比拒绝启动更难排查。

## 鉴权

### 所有请求都返回 `401`

设了 `JEV_API_TOKEN`。要么带上 `Authorization: Bearer <token>`，要么临时取消该变量（仅限本地）。注意仪表盘也要能过鉴权——目前仪表盘不发送该头，配了 token 时页面会显示「无法读取运行列表」，这是预期行为，不是故障。

## 确认

### 点批准后返回 `409`，提示摘要不一致

页面上的待确认信息已经过期。一次批准绑定 `task + action + arguments`，运行重新合成参数后摘要就变了。刷新页面取新的 `digest` 再批准。

### 点批准后返回 `409`，提示当前没有在等待确认

三种可能：已经回应过了、已经超过 `JEV_CONFIRMATION_TTL_SECONDS`、运行早就结束了。查 `GET /tasks/{id}` 看当前状态——如果已经是终态，那这次批准本来就无处可去。

### 运行一直停在 `awaiting_confirmation`，几分钟后自己变成 `needs_confirmation`

确认是阻塞式的：运行原地等你，不推进也不消耗预算。超过 TTL 按「没批准」处理，因此以 `needs_confirmation` 结束。这不是 bug；悬着的确认不该在几小时后突然生效。

### 想让确认等更久

调大 `JEV_CONFIRMATION_TTL_SECONDS`。但这本质上是在放宽「批准的有效期」，属于安全决策，不要为了省事改得很大。

## 运行

### 状态一直是 `running`

正常，模型调用是异步的，单步通常 1–2 秒，委托 LLM 时可能 7–30 秒。用 `/tasks/{id}/traces` 看已经完成的步骤。真卡住了看下一条。

### 终态 `budget_exhausted`

步数或模型调用用完了。默认 8 步 / 16 次调用。若目标本来就需要更多步，先调 `JEV_MAX_STEPS` 与 `JEV_MAX_MODEL_CALLS`（两者要保持 2 倍关系）；若反复在同一处绕圈，那是路由或验证的问题，加预算只会让它绕得更久。

### 终态 `failed`，诊断是 `路由请求失败：transport`

Jev 请求超时或网络不通。先看是不是长尾——实测 p95 约 2 秒，但偶发会到 30 秒以上并撞上默认超时。把 `JEV_TIMEOUT_SECONDS` 提到 60。

### 终态 `failed`，诊断里点名 `LLM_MAX_TOKENS`

推理模型把预算耗在思考上，还没产出内容就结束了，`completion.text` 是空串。这不是解析问题：把 `LLM_MAX_TOKENS` 提到 8192 后同样的输入立刻返回合法 JSON。同时记得把 `LLM_TIMEOUT_SECONDS` 调大，否则会从「空内容」变成「超时」。

### 终态 `failed`，诊断是「路由要求委托，但没有配置委托处理器」

没配 LLM。这是 fail closed 的默认行为：`LLM_API_KEY` 与 `LLM_MODEL` 都没给时，委托分支会明确停下，而不是假装成功。要用就成对配好；不用就把目标改写成不需要深度推理的形式。

### 终态 `failed`，诊断是「状态没有变化，验证器也认为没有进展」，但工作其实做完了

这是「验证器保守 + 完成阈值偏高」的组合，不是执行出错。看 trace 就能确认：最后一步 `executed: true`，结果里是真实的写入/计算结果，只是 `completion_probability` 没够到阈值。

机制：验证不通过就带着状态回到路由；下一次验证仍不通过、而状态在这之间没有推进，就判 `failed`——这条规则是为了避免把同一份 payload 反复发给 provider 直到预算耗尽，它本身没问题。

实测里一条把文件写好的任务，验证器给 0.69，默认阈值 0.75，于是两次都不过、最终失败。按这个顺序排查：

1. 先确认工作真的完成了（去看工具结果与副作用，不要只看状态）。
2. 如果验证器对「明显完成」的任务普遍打 0.65–0.7，把 `JEV_COMPLETION_THRESHOLD` 降到 0.65。实测这样同一场景第 1 步就 `completed`。
3. 如果只是个别任务，别动全局阈值——那是用例或目标描述的问题，全局放宽会让真正没做完的任务也被认成完成。

不确定该不该放宽时，看 `/policy` 页与 trace 里的完成概率分布，不要凭单次失败改。

### 终态 `failed`，诊断是工具拒绝了输入

看诊断里点名的字段。常见两种：参数合成给出了工具 schema 不接受的字段（模型的输出始终是不可信输入，最终由工具校验），或者根本没合成出参数（未配置 LLM 时 resolver 返回空）。

写文件相关的还有三种独立限制：路径必须是相对路径且落在 `JEV_WORKSPACE_ROOT` 内；默认拒绝覆盖已存在的文件；单文件有字节上限。这三种都由工具自己拒绝，与策略是否批准无关——**批准不等于一定成功**。

## 评测

### `calibrate` 说「没有可重放的用例」

报告太旧，缺 `confidence` / `risk` / `requires_confirmation_probability` / `needs_reasoning_probability`。信号是后来才加上去记录的，早期报告没有这些字段也就无法离线重放。重跑一次 `--mode compare` 生成新报告。

### `calibrate` 的推荐值和当前值差得很远，而且全部落在网格边沿

先看它自己打印的两行提示。`inert_dimensions` 说明这些维度在本批用例上根本不影响结果——那就不要改，推荐值只是同分任取。`at_boundary` 说明真实最优可能在网格之外，这时结果只能读作「这个范围内最好」。两种情况的正确处理都是补用例，而不是盲目扩大网格。见 [阈值校准](calibration.md)。

### 评测退出码不是 0

| 码 | 含义 |
| --- | --- |
| `1` | 有用例出错（其他用例的结果仍然有效，报告也已写出） |
| `2` | 配置或用例文件有问题，一个用例都没跑 |
| `3` | 报告没能投递给 API（`--api` 指定的地址不可达或拒收） |

注意 `1` 不代表整轮失败：报告里只有出错的那几行有 `error`，其余照常统计。

### 评测跑得特别慢

LLM 基线是瓶颈。推理模型单条 7–30 秒，53 条就是几分钟。只想看 Jev 侧用 `--mode jev`，快一个数量级。想更便宜地迭代，先用 `--limit 5` 跑前几条确认配置通了。

## 仪表盘

### 页面显示「无法读取运行列表」

先确认 API 在跑：`curl -s http://127.0.0.1:8000/policy`。这条不打 provider，是最快的探活。

API 换了端口就用 `API_UPSTREAM_URL=http://127.0.0.1:9000 npm run dev`。配了 `JEV_API_TOKEN` 而仪表盘没带凭证时也会是这条提示。

### 列表是空的，但我知道之前跑过任务

运行列表是 API 进程内的注册表，不是数据库查询。API 重启后列表从空开始，旧 task id 返回 404。`traces.db` 里的历史记录没丢，只是仪表盘没有「按 id 读历史任务」的入口。

### `npm run build` 报 `broker denied delete: …/.next/types`

这是本机沙箱拦截删除操作导致的，不是代码或 Next 配置的问题。`rm -rf .next` 后重新构建即可。CI 上没有这个拦截。

## 测试

### `pytest` 出现大量 `FileExistsError: …/pytest-of-<user>`

本机沙箱的 `mkdir` 拦截与 pytest 的临时目录创建冲突，与代码无关。换一个基底目录即可：

```sh
uv run pytest --basetemp=$PWD/.pytest_tmp
```

`.pytest_tmp/` 已在 `.gitignore` 里。

### 全新克隆上 `tsc` 报 `Cannot find name 'PageProps'`

Next 16 把 `PageProps` / `LayoutProps` 生成为 `.next/types` 下的全局类型，只有跑过 `dev`、`build` 或 `typegen` 才存在。`npm run typecheck` 现在会先执行 `next typegen`，正常不会有这个问题；如果你绕过它直接跑 `npx tsc --noEmit`，就会撞上。

## 还解决不了

把 `diagnostic`、`policy_reason` 与那条 `trace` 一起贴出来。这两处字段就是为排查留下的：前者说明运行为什么停，后者说明那一步的原始信号与策略结论分别是什么。
