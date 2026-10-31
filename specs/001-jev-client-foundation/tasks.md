# 任务：Jev 客户端基础

## 阶段 1：环境搭建

- [x] T001 在 `pyproject.toml` 和 `uv.lock` 中创建 Python 包元数据、受支持的依赖分组以及锁定文件。
- [x] T002 [P] 在 `jev_router/__init__.py` 和 `jev_router/clients/__init__.py` 中添加包初始化文件。
- [x] T003 [P] 在 `docs/development.md` 中更新开发命令与配置指引。

## 阶段 2：基础设施

- [x] T004 在 `jev_router/clients/jev.py` 中定义脱敏的客户端错误类别以及有限的超时配置。
- [x] T005 在 `jev_router/clients/jev.py` 中定义类型化的、与 JSON 兼容的请求原语和共享校验辅助函数。
- [x] T006 在 `pyproject.toml` 中配置 pytest、异步测试和静态检查设置。

## 阶段 3：用户故事 1 —— 类型化的决策问题

**目标**：把 `noul`、`choice` 和 `score` 问题一起提交，并接收经校验的类型化答案。

**独立测试**：模拟请求与文档所述的线上形态一致，全部三种答案变体都能往返，包括混合的具名问题；格式错误或类型不匹配的答案会安全失败。

- [x] T007 [US1] 模型发现不在本特性范围内；由调用方提供模型标识符。
- [x] T008 [P] [US1] 在 `tests/test_jev_client.py` 中添加针对问题序列化、全部答案变体、混合响应、I/O 之前校验以及脱敏的测试。
- [x] T009 [US1] 在 `jev_router/clients/jev.py` 中实现类型化的问题定义及其请求约束。
- [x] T010 [US1] 在 `jev_router/clients/jev.py` 中实现类型化的 Noul、Choice、Score 答案以及决策响应校验。
- [x] T011 [US1] 在 `jev_router/clients/jev.py` 中实现异步 `/v1/systemone` 请求序列化与响应解析。
- [x] T012 [US1] 在 `jev_router/clients/jev.py` 中将传输、超时、HTTP、JSON 和 schema 失败转换为脱敏的类型化错误，且不重试。

## 阶段 4：用户故事 2 —— 安全的客户端配置

**目标**：在源代码之外配置端点、凭据和超时，同时避免机密泄露。

**独立测试**：合法与非法配置都会产生确定性的行为；对外错误和日志都不会暴露所配置的凭据。

- [x] T013 [P] [US2] 在 `tests/test_jev_client.py` 中添加离线传输测试，覆盖超时、网络失败、HTTP 状态、非法 JSON／schema、不重试以及机密脱敏。
- [x] T014 [US2] 在 `jev_router/clients/jev.py` 中加载并校验环境配置，且不记录机密取值。
- [x] T015 [US2] 在 `docs/development.md` 中记录依赖安装以及显式选择模型的客户端设置。

## 阶段 5：收尾打磨

- [x] T016 运行格式化／lint、静态类型检查和完整的离线测试套件；修正 `pyproject.toml`、`jev_router/clients/jev.py` 和 `tests/test_jev_client.py` 中的失败。
- [x] T017 验证 `.gitignore` 中的 `.env` 忽略规则，并在不打印本地机密内容的前提下审计生成的测试／文档／错误中是否含凭据。本工作区不是 Git 仓库，因此无法进行基于 Git 的忽略验证。

## 依赖关系

- T001 先于 T006 以及所有测试执行。
- T002 和 T004–T006 是用户故事的基础。
- 用户故事 1 和用户故事 2 在基础完成之后可以独立测试；它们需谨慎共用客户端模块。
- T016–T017 在实现之后执行。

## 并行机会

- T001 之后：T002 和 T003 可以独立推进。
- 基础搭建完成之后：如果接口协调一致，测试可以与相应的客户端代码并行开发。

## 实施策略

将可用的 `/v1/systemone` 客户端作为 MVP 交付。由调用方提供模型标识符；模型发现和后续的 V1 阶段不在本特性范围内。先用离线模拟进行验证，然后最终确定配置与文档。
