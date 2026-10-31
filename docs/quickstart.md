# 快速开始

从克隆到看见一次完整运行，大约五分钟。除了 Jev 的 API key，不需要别的外部服务。

## 前置条件

| 依赖 | 版本 | 检查命令 |
| --- | --- | --- |
| Python | 3.9 及以上 | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | 任意较新版本 | `uv --version` |
| Node.js | 20.9 及以上（仅仪表盘需要） | `node --version` |
| Jev 凭证 | `JEV_API_KEY` 与 `JEV_MODEL` | TypeSafe 控制台 |

只跑核心与测试不需要 Node；只想看命令行行为的话，跳过 Web 那两节。

## 1. 安装依赖

```sh
git clone https://github.com/HangChi/JevRouter.git
cd JevRouter
uv sync --all-groups
```

`--all-groups` 会连开发依赖（pytest / ruff / mypy）一起装上；只跑服务可以省掉它。

## 2. 配置凭证

```sh
cp .env.example .env
```

然后编辑 `.env`，至少要填这两个：

```ini
JEV_API_KEY=<你的 key>
JEV_MODEL=<你的账号可用的模型 id>
```

模型 id 不要猜。`jev-latest` 是本文档实测过的值，但你的账号未必开通了同一个；用控制台列出的那个。

可选地再配 LLM（用于「委托给 LLM」分支和工具参数合成）。**不配也能跑**，只是遇到需要委托的步骤会 `fail closed` 停下——这是设计，不是故障：

```ini
LLM_API_KEY=<你的 LLM key>
LLM_BASE_URL=https://api.anthropic.com
LLM_API_STYLE=messages
LLM_MODEL=claude-sonnet-4-5
```

所有变量与语义见 [配置参考](configuration.md)。

## 3. 启动 API

```sh
uv run --env-file .env uvicorn apps.api.app:create_app --factory --port 8000
```

`--env-file` 是必须的：凭证只从这个进程的环境变量读，代码里没有默认值。

看到 uvicorn 的启动日志后，另开一个终端确认它在：

```sh
curl -s http://127.0.0.1:8000/policy | python3 -m json.tool
```

应当返回当前生效的阈值与工具风险表。这条命令同时也是最快的连通性检查——它不打 provider，不花钱。

## 4. 提交第一个任务

用 calculator，因为它一步完成、不需要确认、不产生副作用：

```sh
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"goal": "计算 (12 + 8) * 3"}' | python3 -m json.tool
```

返回里有 `task_id`，用它查结果：

```sh
curl -s http://127.0.0.1:8000/tasks/<task_id> | python3 -m json.tool
curl -s http://127.0.0.1:8000/tasks/<task_id>/traces | python3 -m json.tool
```

第一次查询时状态可能还是 `running`，稍等一两秒再看。预期终态是 `completed`，`traces` 里有一条 `calculator` 步骤，`result` 含 `{"value": 60}`。

## 5. 启动仪表盘（可选）

```sh
cd apps/web
npm install
npm run dev
```

打开 http://127.0.0.1:3000 。上游地址默认 `http://127.0.0.1:8000`，API 换了端口就用环境变量覆盖：

```sh
API_UPSTREAM_URL=http://127.0.0.1:9000 npm run dev
```

仪表盘只连 API，不持有任何 provider 凭证——所有请求都发生在 Next.js 服务端。

## 6. 试一次需要确认的任务

写文件属于 `write` 风险，策略引擎无条件要求确认，与模型给出的概率无关：

```sh
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"goal": "把这句话写进 demo/hello.txt：JevRouter 快速开始"}' | python3 -m json.tool
```

状态会停在 `awaiting_confirmation`，`pending_confirmation` 里带 `action`、合成后的 `arguments`、`digest` 与 `expires_at`。批准它：

```sh
curl -s -X POST http://127.0.0.1:8000/tasks/<task_id>/confirm \
  -H 'content-type: application/json' \
  -d '{"approved": true, "digest": "<上一步返回的 digest>"}'
```

`digest` 不能省，也不能自己编——它把这次批准钉在「哪个任务、哪个动作、哪份参数」上。参数变了，旧批准立刻失效。超过 `JEV_CONFIRMATION_TTL_SECONDS`（默认 900 秒）没回应，按未批准处理。

默认工作区是仓库根的 `workspace/`，文件会落在 `workspace/demo/hello.txt`。

## 7. 跑一次评测

评测会真实调用 provider，**产生费用**：

```sh
uv run --env-file .env python -m evals --mode compare --json-out evals-report.json
```

`compare` 同时跑 Jev 与 LLM 基线，53 条用例，大致几分钟。只想省钱地看 Jev 侧就用 `--mode jev`；不想花钱就先看下面这条——它读已有报告，零调用。

跑完可以在 `/evals` 页看到结果，也可以拿去校准阈值：

```sh
uv run python -m evals --mode calibrate --from-report evals-report.json --top 10
```

详见 [阈值校准](calibration.md)。

## 8. 确认自己没弄坏什么

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest
```

测试全部使用 HTTP mock 与临时数据库，不需要凭证、不产生调用。前端另有 `cd apps/web && npm run typecheck && npm test`。

## 遇到问题

- 服务起不来、确认总是 409、评测报空内容、`tsc` 报 `PageProps` —— 见 [故障排查](troubleshooting.md)。
- 想知道每个变量的含义 —— 见 [配置参考](configuration.md)。
- 想知道策略为什么这么判 —— 见 [架构与模块边界](architecture.md) 与 [安全与策略边界](security.md)。
