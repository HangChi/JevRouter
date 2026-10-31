# 快速开始：Web trace 看板

看板是第 9 阶段 API 的读取方。先启动 API，再启动 Web 应用。

```sh
# Terminal 1 — the API (needs a real credential for live runs)
export JEV_API_KEY="your-key"
export JEV_MODEL="jev-latest"
export JEV_DATABASE_PATH="./traces.db"
uv run uvicorn apps.api.app:create_app --factory --reload
```

```sh
# Terminal 2 — the dashboard
cd apps/web
npm install
npm run dev
```

打开 <http://localhost:3000>。看板从 `API_UPSTREAM_URL` 读取 API，该变量默认为 `http://127.0.0.1:8000`：

```sh
# apps/web/.env
API_UPSTREAM_URL=http://127.0.0.1:8000
```

从首页提交一个目标，然后顺着链接进入它的任务页面。一个 `write` 或 `external` 风险的动作会让运行暂停；任务页面会展示该动作及其已解析的参数，并等待批准或否决。

供应商凭据留在 API 进程中。浏览器只与 Next.js 服务器通信，而 Next.js 服务器是唯一知道 `API_UPSTREAM_URL` 的组件。

## 检查

```sh
cd apps/web
npx tsc --noEmit
npm run test
npm run build
```

Python 检查未改动，且保持全绿，因为本阶段不触碰任何 Python 文件：

```sh
uv run ruff check .
uv run mypy jev_router apps
uv run pytest
```
