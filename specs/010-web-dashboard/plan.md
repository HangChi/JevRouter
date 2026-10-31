# 实施计划：Web trace 看板

## 摘要

新增 `apps/web/`：一个 Next.js 应用，在服务端读取 `apps/api` 的六个端点，渲染任务列表与逐步骤的 trace 视图，并回应运行提出的确认与输入提示。不改动任何 Python 代码。

## 技术背景

- API：第 9 阶段的 `apps/api`，六个端点，严格的响应模型，`404`/`409`/`422`/`400` 错误映射。
- 核心：`jev_router` 未被触碰。看板只是 HTTP 响应的消费者。
- 运行时：Node 与 npm；Next.js App Router、React、TypeScript、Tailwind。
- 测试：用 vitest 测试纯视图模型与带桩 fetch 的 API 客户端；用 `tsc --noEmit` 与 `next build` 作为静态检查。

## 设计

### 仅服务端的 API 访问

浏览器绝不调用 `apps/api`。`src/lib/api.ts` 在服务端运行——读取时在服务端组件中，写入时在服务端动作中——并通过 `API_UPSTREAM_URL` 访问 API。由此产生两个结果：

- `apps/api` 中不需要任何 CORS 配置，也没有添加任何 CORS 配置。
- 任何凭据都无法抵达浏览器，因为系统中唯一的凭据是由 Python 进程从它自己的环境中读取的。

这正是本阶段不改动任何 Python 文件的原因：一个浏览器直连 API 的设计，会迫使第 9 阶段的应用工厂做一次 CORS 改动。

### 读取走服务端组件；页面依然会更新

运行是实时的，因此纯粹服务端渲染的页面会变旧。一个小小的客户端岛（`<LiveRefresh intervalMs>`）按间隔调用 `router.refresh()`；服务端组件会重新运行并以新数据重新渲染。任务进入终态后该岛会自行停止，因此已结束的运行不再产生任何请求。选择轮询而非流式，是因为 API 没有流式端点，而新增一个是范围之外的事。

### 写入走服务端动作

`submitTask`、`confirmTask` 与 `provideInput` 是服务端动作，它们调用 API，然后对受影响的路径执行 `revalidatePath`。`409` 意味着运行在渲染与点击之间已经继续，因此动作返回 API 的消息，页面把它渲染为一条提示，而不是假装答案已经送达。

### 视图模型与渲染分离

把 `TraceView` 转成可展示内容的一切，都是 `src/lib/viewModel.ts` 中的纯函数。组件负责布局与样式；它们不决定某个状态意味着什么、某个步骤走了哪条分支，或者某个阈值是否被越过。这正是让那些真正有意思的逻辑无需 DOM 即可测试的原因。

### 对概率与评分的诚实渲染

四个路由信号中有三个是位于 `[0, 1]` 的 `noul` 概率，会被绘制为带阈值标记的计量条。`route_risk` 是跨五个等级的供应商评分，`quality_score` 是跨四个等级的评分，因此它们被绘制为数字加一条等级条，原始值始终可见。缺失的字段渲染为「—」，绝不渲染为零：一个 `NULL` 列与一个真实的 `0.0` 含义并不相同。

### 布局

宽视口下分两栏：左侧任务列表，右侧选中的任务。窄视口下列表折叠到详情之上。步骤链条作为一条紧凑的有序条带横贯详情视图顶部，其下方每个步骤一张卡片。颜色只具有语义——结果色调与阈值越界——数字使用等宽字体，以便成列的数字对齐。

## 文件

```text
apps/web/
├── package.json, tsconfig.json, next.config.ts, vitest.config.ts, postcss.config.mjs
├── .env.example, README.md
└── src/
    ├── app/
    │   ├── layout.tsx, globals.css, page.tsx, not-found.tsx
    │   └── tasks/[taskId]/page.tsx
    ├── lib/
    │   ├── types.ts, thresholds.ts, api.ts, viewModel.ts
    │   └── *.test.ts
    ├── components/
    │   ├── LiveRefresh.tsx, StatusBadge.tsx, TaskList.tsx, SubmitForm.tsx
    │   ├── PendingPrompt.tsx, DecisionChain.tsx, StepCard.tsx
    │   ├── ProbabilityMeter.tsx, ScoreReadout.tsx, JsonBlock.tsx
    │   └── ApiNotice.tsx
    └── actions/tasks.ts
```

## 非目标

与规格说明相同：不做认证、不做流式、不改动 `apps/api`、不做评测相关工作。

## 验证策略

1. `npx tsc --noEmit` —— 镜像的类型能够编译。
2. `npm run test` —— 用 vitest 跑视图模型与带桩的 API 客户端。
3. `npm run build` —— 生产构建，它同时会做类型检查并静态渲染两个路由。
4. 在 uvicorn 下、针对临时数据库并以桩化的 Jev 客户端启动 `apps/api`，通过看板提交一个任务、批准一个待处理的确认，并用 curl 读取渲染出的页面。
5. `uv run ruff check .`、`uv run mypy jev_router apps`、`uv run pytest` —— 未改动，且预期保持全绿。
