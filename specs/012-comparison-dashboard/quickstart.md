# 快速开始：对比看板

## 运行检查

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest

cd apps/web
npx tsc --noEmit
npm run test
npm run lint
npm run build
```

## 记录一次运行并读回

启动 API（其数据库保存这些运行记录）：

```sh
export JEV_API_KEY=... JEV_MODEL=...
export LLM_API_KEY=... LLM_MODEL=...
uv run uvicorn apps.api.app:create_app --factory
```

运行评测并提交报告：

```sh
uv run python -m evals --mode compare --api http://127.0.0.1:8000
```

然后读回：

```sh
curl -s localhost:8000/evals
curl -s localhost:8000/evals/<run_id> | python3 -m json.tool
```

`--json-out PATH` 会改为在本地写出同一份报告，也可以两者并行。

## 在看板中查看

```sh
cd apps/web
API_UPSTREAM_URL=http://127.0.0.1:8000 npm run build && npm run start
```

- <http://localhost:3000/evals> — 已记录的运行，以及最新一次运行的聚合卡片。
- <http://localhost:3000/evals/<run_id>> — 每个用例一行，包含两个路由层各自的动作、延迟、Token 与是否一致。

## 值得了解的错误路径

| 情形 | 返回 |
| --- | --- |
| `GET /evals/<unknown>` | `404 {"detail": "eval run not found"}` |
| `GET /evals?limit=0` | `400 {"detail": "limit must be positive"}` |
| `POST /evals` 携带未知模式、未配对的 compare 行或未知字段 | `422` |
| `--api` 不可达或被拒绝 | 退出码 `3`，API 的消息输出到 stderr |

## 这些页面刻意不做的事

- 不做轮询：与进行中的任务不同，一次评测运行是一份已完成的记录。
- 对某个模式无法产出的指标不显示零：LLM 基线没有策略判定结果，因此它的升级与确认卡片为缺失状态，而当某路由层出错时，行级的一致性单元格为空白。
- 不重新计算：API 存储报告携带的比率，因此看板与命令行摘要始终一致。
