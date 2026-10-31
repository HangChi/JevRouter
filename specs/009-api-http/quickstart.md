# 快速开始：API HTTP 边界

```sh
export JEV_API_KEY="your-key"
export JEV_MODEL="jev-latest"
export JEV_DATABASE_PATH="./traces.db"
export JEV_WORKSPACE_ROOT="./workspace"

uv run uvicorn apps.api.app:create_app --factory --reload
```

交互式文档在 `http://127.0.0.1:8000/docs` 提供。

```sh
# Start a run; the response is immediate, the run continues in the background.
TASK=$(curl -s -X POST localhost:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"goal": "Calculate 2 + 2"}' | jq -r .task_id)

# Poll until it leaves the live states.
curl -s localhost:8000/tasks/$TASK | jq

# Read the traces as they accumulate.
curl -s localhost:8000/tasks/$TASK/traces | jq
```

一个 `write` 或 `external` 风险的动作会让运行暂停：

```sh
curl -s localhost:8000/tasks/$TASK | jq '.status, .pending_confirmation'
# "awaiting_confirmation"
# { "action": "write_file", "arguments": { "path": "note.txt", "content": "hello" }, "step": 0 }

curl -s -X POST localhost:8000/tasks/$TASK/confirm \
  -H 'content-type: application/json' -d '{"approved": true}'
```

凭据仅由服务进程从环境中读取。它永远不会成为某个请求、某个响应或某条已存储 trace 的一部分。

用 `uv run pytest tests/test_api.py` 运行离线检查，并运行完整的项目检查。
