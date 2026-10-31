# 任务：对比看板

## 阶段 1：持久化与 HTTP 边界

- [x] T001 为 `apps/api/storage.py` 增加 `eval_runs` 与 `eval_case_results`，把 `SCHEMA_VERSION` 升到 2，并用既有的外层结构编解码与 upsert 幂等性实现 `record_eval_run`、`list_eval_runs` 与 `load_eval_run`；覆盖往返读写、重复记录同一 id，以及 version-1 数据库仍可打开。
- [x] T002 在 `apps/api/schemas.py` 中为记录与读取一次评测运行添加严格的 payload 模型与视图模型。
- [x] T003 为 `apps/api/app.py` 添加 `POST /evals`、`GET /evals` 与 `GET /evals/{run_id}`，沿用既有的错误映射（`404` 未知运行、`422` 非法请求体、`400` 错误的 limit），并在 `tests/test_api.py` 中覆盖它们。

## 阶段 2：命令行桥接

- [x] T004 为 `evals/cli.py` 添加 `--api URL`：在一次运行结束后，使用 API 自己的 payload 模型把报告 POST 到 `POST /evals`，将非 2xx 响应作为失败上报并附上 API 的消息。

## 阶段 3：Web 看板

- [x] T005 在 `apps/web/src/lib/types.ts` 中镜像评测传输类型。
- [x] T006 为 `apps/web/src/lib/api.ts` 添加 `listEvalRuns` 与 `getEvalRun`，并用桩化的 fetch 覆盖它们。
- [x] T007 为 `apps/web/src/lib/viewModel.ts` 添加评测视图模型：按模式的聚合卡片、一致性色调、逐用例对比行，以及比率、时长与 Token 计数的格式化；对其做单元测试，包含缺失指标与单侧运行的情形。
- [x] T008 构建 `apps/web/src/app/evals/page.tsx`：运行列表，每次运行一组卡片，以及 API 不可用提示与空状态。
- [x] T009 构建 `apps/web/src/app/evals/[runId]/page.tsx`：逐用例对比表，含期望动作、两种模式的动作、是否一致、延迟、Token 与错误，以及未知运行的未找到页面。
- [x] T010 在看板头部添加评测链接。

## 阶段 4：检查、验证与文档

- [x] T011 在 `apps/web` 中运行 `tsc --noEmit`、vitest、eslint 与 `next build`；修复它们报告的所有问题。
- [x] T012 端到端验证：用临时数据库在 uvicorn 下启动 `apps.api`，通过 curl 驱动 `POST /evals` 记录一次预置好的 compare 运行，再通过 `GET /evals/{run_id}` 读回，并用 curl 针对该 API 渲染两个看板页面。
- [x] T013 更新 `README.md`、`docs/development.md`、`docs/architecture.md` 与 `apps/web/README.md`，以覆盖评测端点与页面；记录新的 schema 版本。
- [x] T014 编写本规格目录下的 `data-model.md` 与 `quickstart.md`，然后运行完整的项目检查（ruff、对 `jev_router apps evals` 的严格 mypy、pytest）。

## 依赖关系

T001 先于 T002/T003。T003 先于 T004。T005–T007 先于 T008/T009。T010 独立。T011–T014 在实施之后进行。

## 完成标准

所有任务只有在实施与验证之后才会被勾选。本阶段不改动任何指标定义，且 `evals/` 除命令行用于 `--api` 桥接的 payload 模型之外，仍然不从 `apps/` 导入任何内容。
