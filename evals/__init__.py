"""针对 JevRouter 路由决策的离线评测包。

评测库只依赖 ``jev_router`` 的公共接口：固定的用例集会通过智能体所用的同一套
Router、PolicyEngine 和工具重放，另外还有一个用于对比的 LLM 基线路由层。
``evals.cli`` 是唯一允许跨入 ``apps/`` 的模块（用于提交报告），并且是通过
HTTP 完成的。
"""
