# 任务：工具注册表与 MVP 工具

## 阶段 1：基础

- [x] T001 在 `jev_router/tools/base.py` 中定义工具协议、风险级别和结构化结果。
- [x] T002 [P] 在 `jev_router/tools/registry.py` 中实现可信内存注册表的注册、查找与派发。
- [x] T003 [P] 在 `jev_router/tools/__init__.py` 中添加公开导出。

## 阶段 2：MVP 工具

- [x] T004 在 `jev_router/tools/calculator.py` 中实现基于 AST 允许列表的有边界算术求值。
- [x] T005 在 `jev_router/tools/knowledge_search.py` 中实现注入式本地知识搜索与有界摘录。
- [x] T006 在 `jev_router/tools/web_search.py` 中实现仅使用夹具的模拟网页搜索。
- [x] T007 在 `jev_router/tools/write_file.py` 中实现受根目录约束的文件写入、大小限制、符号链接包含以及默认不覆盖。
- [x] T008 在 `jev_router/tools/mock_email.py` 中实现经校验、仅在本地生效的模拟邮件。

## 阶段 3：测试与文档

- [x] T009 在 `tests/test_tools.py` 中覆盖注册表和 MVP 工具的成功／错误边界。
- [x] T010 在 `docs/development.md` 和 `docs/security.md` 中记录工具用法与安全边界。
- [x] T011 在本规格目录中定义阶段范围、架构、数据模型和离线快速开始。
- [x] T012 运行 Ruff、严格模式的 mypy 以及完整的离线 pytest 套件；所有检查均通过。
- [x] T013 复核文件系统边界假设，并确认没有引入任何真实网络／服务行为。配置的根目录必须受到保护，以防敌对的并发符号链接替换。

## 依赖关系

T001 先于 T002–T008。每个工具的实现先于其边界测试。T012–T013 在实现与文档之后执行。

## 完成标准

所有任务仅在其实现与验证完成之后才会被勾选。本阶段不包含任何路由层、策略引擎、执行循环（Runner）、API、仪表盘、持久化或真实集成。
