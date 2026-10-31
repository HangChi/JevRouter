/**
 * `jev_router/policy.py` 里的阈值、以及执行循环的完成阈值，在这里的「仅用于显示」副本。
 *
 * 这些常量现在只是画刻度用的显示副本：仪表上的刻度线位置由它们决定。真正的权威
 * 是 API 的 `GET /policy`；仪表盘报告的结论始终来自 API 的 `policy_outcome`。
 * 两者一旦漂移，刻度会画错，但结论仍然来自 API、依然正确。之所以把它们放在同一个
 * 模块，是为了让这种漂移只有一处需要修。
 */

/** 路由置信度低于此值时，交给 LLM 处理。 */
export const ROUTE_CONFIDENCE_THRESHOLD = 0.75;

/** 确认概率高于此值时，向用户请求确认。 */
export const CONFIRMATION_THRESHOLD = 0.75;

/** 推理需求高于此值时，这一步交给 LLM 处理。 */
export const REASONING_THRESHOLD = 0.7;

/** 风险分达到或高于此值时，向用户请求确认。 */
export const RISK_THRESHOLD = 2.5;

/** 执行循环判定任务已完成所用的完成阈值。 */
export const COMPLETION_THRESHOLD = 0.75;

/**
 * 仪表盘渲染的两个提供方分数所用的等级数量。`route_risk` 按路由层提交的五个
 * 风险等级计分；`quality_score` 按验证器的四级图例计分。核心包不会对提供方的
 * 分数字段做归一化，因此这些等级数是对「从 0 开始的索引刻度」的一个假设——
 * 原始数字始终渲染在刻度条旁边。
 */
export const RISK_LEVEL_COUNT = 5;
export const QUALITY_LEVEL_COUNT = 4;
