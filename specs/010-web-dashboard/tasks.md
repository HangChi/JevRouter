# 任务：Web trace 看板

## 阶段 1：脚手架与传输

- [x] T001 把 `apps/web/` 搭建成一个使用 TypeScript、Tailwind 与导入别名的 Next.js App Router 项目；在其 README 中记录对 Node 工具链的预期。
- [x] T002 在 `src/lib/types.ts` 中镜像 `apps/api/schemas.py`，并记录这份镜像。
- [x] T003 新增 `src/lib/thresholds.ts`，内含核心 MVP 阈值的仅展示用镜像。
- [x] T004 实现 `src/lib/api.ts`，含可注入的 fetch、`ApiError` 与 `ApiUnavailableError`，以及 `API_UPSTREAM_URL` 解析。
- [x] T005 新增 `.env.example`，只记录 `API_UPSTREAM_URL`，别无其他。

## 阶段 2：视图模型

- [x] T006 在 `src/lib/viewModel.ts` 中实现 `statusTone`、`policyBranch`、`probabilityMeters`、`scoreReadouts`、`verificationReadout` 与 `decisionChain`。
- [x] T007 实现格式化函数 `formatDuration`、`formatProbability` 与 `formatScore`。
- [x] T008 对视图模型做单元测试，包括缺失字段、未知状态与未知策略结果。
- [x] T009 对带桩 fetch 的 API 客户端做单元测试：路径、方法、请求体、`404`/`409` 映射以及上游不可用的情况。

## 阶段 3：页面与组件

- [x] T010 构建任务列表页面，含提交表单与 API 不可用提示。
- [x] T011 构建任务详情页面：头部、待处理提示、决策链条与每个步骤一张卡片。
- [x] T012 渲染概率计量条、评分读数与验证读数，缺失字段用「—」表示。
- [x] T013 新增 `<LiveRefresh>`，使实时任务按间隔刷新并在进入终态时停止。
- [x] T014 接通提交、确认与提供输入三个服务端动作，包括 `409` 提示。
- [x] T015 为未知任务 id 新增未找到页面。

## 阶段 4：检查与文档

- [x] T016 运行 `tsc --noEmit`、vitest 套件与 `next build`；修掉它们报告的一切问题。
- [x] T017 在 uvicorn 下、以桩化的 Jev 客户端与临时数据库启动 `apps/api`，然后用 curl 通过看板实际走一遍提交、确认与 trace 读取。
- [x] T018 编写 `apps/web/README.md`，涵盖安装设置、配置与检查。
- [x] T019 为 Web 层更新 `README.md`、`docs/architecture.md` 与 `docs/development.md`。
- [x] T020 在本规格目录中记录范围、数据模型与阶段边界，并运行完整的项目检查。

## 依赖关系

T001–T005 先于 T006–T015。T016–T020 在实现之后进行。

## 完成标准

所有任务只有在实现与验证之后才会被勾选。本阶段中 `jev_router/` 或 `apps/api/` 下没有任何文件被改动。
