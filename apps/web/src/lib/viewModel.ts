import {
  COMPLETION_THRESHOLD,
  CONFIRMATION_THRESHOLD,
  QUALITY_LEVEL_COUNT,
  REASONING_THRESHOLD,
  RISK_LEVEL_COUNT,
  RISK_THRESHOLD,
  ROUTE_CONFIDENCE_THRESHOLD,
} from "./thresholds";
import type { EvalComparisonMetrics, EvalModeMetrics, EvalCaseOutcome, TraceView } from "./types";

/**
 * API 传输类型之上的纯视图模型。
 *
 * 这里不碰 React、网络或 DOM：组件负责布局与样式，而这个模块决定一个状态是什么
 * 意思、一个步骤走了哪个分支、以及某个阈值是否被跨过。正是这条分界让真正有意思
 * 的逻辑无需渲染任何东西就能被测试。
 */

export type Tone = "neutral" | "live" | "blocked" | "good" | "bad";

/**
 * 一个步骤走的是哪个分支，由策略结论加上实际发生了什么推导出来。`executed`
 * 优先级最高：一个被批准并执行了的动作就是已执行的动作，不管它是怎么走到那里的。
 */
export type Branch =
  | "executed"
  | "denied"
  | "approved_failed"
  | "rejected"
  | "delegated"
  | "asked"
  | "finished"
  | "not_executed"
  | "unknown";

/** API 没有返回某个字段时，就在该字段的位置渲染这个值。 */
export const ABSENT = "—";

const LIVE_STATUSES = new Set(["running", "awaiting_confirmation", "awaiting_input"]);
const BLOCKED_STATUSES = new Set([
  "awaiting_confirmation",
  "awaiting_input",
  "needs_confirmation",
  "needs_user_input",
]);
const GOOD_STATUSES = new Set(["completed"]);
const BAD_STATUSES = new Set(["rejected", "budget_exhausted", "failed"]);

/**
 * 把传输来的状态映射成呈现用的色调。阻塞状态最先判断，这样一个正在等人处理的
 * 运行会读作「阻塞」而不只是「进行中」；任何无法识别的值都落到 `bad`，而不是
 * 被画成一切正常的样子。
 */
export function statusTone(status: string): Tone {
  if (BLOCKED_STATUSES.has(status)) {
    return "blocked";
  }
  if (LIVE_STATUSES.has(status)) {
    return "live";
  }
  if (GOOD_STATUSES.has(status)) {
    return "good";
  }
  if (BAD_STATUSES.has(status)) {
    return "bad";
  }
  return "bad";
}

/**
 * 一个运行只在仍在进行时才算「live」。两个因为需要人工介入而结束的终态
 * （`needs_confirmation`、`needs_user_input`）读起来是阻塞，但其实已经结束，
 * 因此对它们也必须停止轮询。
 */
export function isLiveStatus(status: string): boolean {
  return LIVE_STATUSES.has(status);
}

export function policyBranch(trace: TraceView): Branch {
  if (trace.executed) {
    return "executed";
  }
  if (trace.confirmed === false) {
    return "denied";
  }
  if (trace.confirmed === true) {
    // 已批准但从未执行：工具被放行去运行，随后失败了。
    return "approved_failed";
  }
  switch (trace.policy_outcome) {
    case "reject":
      return "rejected";
    case "delegate_to_llm":
      return "delegated";
    case "ask_user":
      return "asked";
    case "finish":
      return "finished";
    case "execute":
    case "ask_confirmation":
      return "not_executed";
    default:
      return "unknown";
  }
}

export interface ProbabilityMeter {
  key: "route_confidence" | "requires_confirmation" | "needs_reasoning" | "completion_probability";
  label: string;
  value: number;
  threshold: number;
  /** 策略引擎把阈值的哪一侧视为触发条件。 */
  direction: "above" | "below";
  /** 按策略里的比较方式，这个信号是否落在触发侧。 */
  crossed: boolean;
}

/**
 * 路由层返回的三个概率，客户端会把它们校验到 `[0, 1]`。比较方式与
 * `jev_router/policy.py` 一致：确认与推理需求在严格高于各自阈值时触发，
 * 置信度则在严格低于自身阈值时触发。
 */
export function probabilityMeters(trace: TraceView): ProbabilityMeter[] {
  const meters: ProbabilityMeter[] = [];
  const push = (
    key: ProbabilityMeter["key"],
    label: string,
    value: number | null,
    threshold: number,
    direction: ProbabilityMeter["direction"],
  ) => {
    if (!isFiniteNumber(value)) {
      return;
    }
    meters.push({
      key,
      label,
      value,
      threshold,
      direction,
      crossed: direction === "above" ? value > threshold : value < threshold,
    });
  };

  push("route_confidence", "路由置信度", trace.route_confidence, ROUTE_CONFIDENCE_THRESHOLD, "below");
  push(
    "requires_confirmation",
    "确认需求",
    trace.requires_confirmation,
    CONFIRMATION_THRESHOLD,
    "above",
  );
  push("needs_reasoning", "推理需求", trace.needs_reasoning, REASONING_THRESHOLD, "above");
  return meters;
}

/**
 * 完成度，用执行循环自己的阈值来度量。它之所以与路由信号分开，是因为它来自
 * 验证器而不是路由层，并且只出现在经过验证的步骤上。
 */
export function completionMeter(trace: TraceView): ProbabilityMeter | null {
  if (!isFiniteNumber(trace.completion_probability)) {
    return null;
  }
  return {
    key: "completion_probability",
    label: "完成度",
    value: trace.completion_probability,
    threshold: COMPLETION_THRESHOLD,
    direction: "below",
    crossed: trace.completion_probability < COMPLETION_THRESHOLD,
  };
}

export interface ScoreReadout {
  key: "route_risk" | "quality_score";
  label: string;
  value: number;
  /** 没有针对它定义阈值的分数为 `null`。 */
  threshold: number | null;
  level: number;
  levelCount: number;
  crossed: boolean;
}

/**
 * 两个提供方分数。`ScoreAnswer.score` 是核心包不做归一化的有限浮点数，因此
 * 它们连同阈值和等级条一起以数字形式上报，从不用 0–1 的仪表来表示。
 */
export function scoreReadouts(trace: TraceView): ScoreReadout[] {
  const readouts: ScoreReadout[] = [];
  if (isFiniteNumber(trace.route_risk)) {
    readouts.push({
      key: "route_risk",
      label: "路由风险",
      value: trace.route_risk,
      threshold: RISK_THRESHOLD,
      level: levelOf(trace.route_risk, RISK_LEVEL_COUNT),
      levelCount: RISK_LEVEL_COUNT,
      crossed: trace.route_risk >= RISK_THRESHOLD,
    });
  }
  if (isFiniteNumber(trace.quality_score)) {
    readouts.push({
      key: "quality_score",
      label: "结果质量",
      value: trace.quality_score,
      threshold: null,
      level: levelOf(trace.quality_score, QUALITY_LEVEL_COUNT),
      levelCount: QUALITY_LEVEL_COUNT,
      crossed: false,
    });
  }
  return readouts;
}

export interface VerificationReadout {
  completionProbability: number;
  completionThreshold: number;
  /** 执行循环在 `>=` 阈值时判定完成。 */
  completionMet: boolean;
  qualityScore: number;
  qualityLevel: number;
  qualityLevelCount: number;
}

/** 只有验证器为该步骤运行过，这一步才带有验证结果。 */
export function verificationReadout(trace: TraceView): VerificationReadout | null {
  if (!isFiniteNumber(trace.completion_probability) || !isFiniteNumber(trace.quality_score)) {
    return null;
  }
  return {
    completionProbability: trace.completion_probability,
    completionThreshold: COMPLETION_THRESHOLD,
    completionMet: trace.completion_probability >= COMPLETION_THRESHOLD,
    qualityScore: trace.quality_score,
    qualityLevel: levelOf(trace.quality_score, QUALITY_LEVEL_COUNT),
    qualityLevelCount: QUALITY_LEVEL_COUNT,
  };
}

export interface ChainNode {
  step: number;
  action: string;
  outcome: string | null;
  branch: Branch;
}

/** 每个步骤一个节点，按步骤顺序排列，构成运行级别的决策链。 */
export function decisionChain(traces: TraceView[]): ChainNode[] {
  return [...traces]
    .sort((left, right) => left.step - right.step)
    .map((trace) => ({
      step: trace.step,
      action: trace.action,
      outcome: trace.policy_outcome,
      branch: policyBranch(trace),
    }));
}

const BRANCH_LABELS: Record<Branch, string> = {
  executed: "已执行",
  denied: "确认被拒绝",
  approved_failed: "已批准但执行失败",
  rejected: "已拒绝",
  delegated: "已委托 LLM",
  asked: "已询问用户",
  finished: "已结束",
  not_executed: "未执行",
  unknown: "未知",
};

/**
 * 传输来的策略结论是稳定的标识符，因此只做显示上的翻译、绝不改写：无法识别的
 * 值原样透传，而不是被折叠进某个已知标签。
 */
const OUTCOME_LABELS: Record<string, string> = {
  execute: "执行",
  ask_confirmation: "请求确认",
  delegate_to_llm: "委托 LLM",
  ask_user: "询问用户",
  finish: "结束",
  reject: "拒绝",
};

/** 进行中与终态的状态，同样按这种方式翻译。 */
const STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  awaiting_confirmation: "等待确认",
  awaiting_input: "等待输入",
  completed: "已完成",
  needs_user_input: "需要用户输入",
  needs_confirmation: "需要确认",
  rejected: "已拒绝",
  budget_exhausted: "预算耗尽",
  failed: "失败",
};

export function branchLabel(branch: Branch): string {
  return BRANCH_LABELS[branch];
}

export function outcomeLabel(outcome: string | null): string {
  if (outcome === null) {
    return ABSENT;
  }
  return OUTCOME_LABELS[outcome] ?? outcome;
}

/** 每个策略结论对应的色调，用于决策链和步骤卡片标题。 */
export function outcomeTone(outcome: string | null): Tone {
  switch (outcome) {
    case "finish":
      return "good";
    case "ask_confirmation":
    case "ask_user":
      return "blocked";
    case "execute":
    case "delegate_to_llm":
      return "neutral";
    case "reject":
      return "bad";
    default:
      return "bad";
  }
}

/** 用运维者的语言表达传输来的状态，标识符保持原样。 */
export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

export function formatDuration(durationMs: number): string {
  if (!isFiniteNumber(durationMs) || durationMs < 0) {
    return ABSENT;
  }
  const rounded = Math.round(durationMs);
  if (rounded < 1000) {
    return `${rounded} ms`;
  }
  return `${(durationMs / 1000).toFixed(2)} s`;
}

export function formatProbability(value: number | null): string {
  return isFiniteNumber(value) ? `${(value * 100).toFixed(1)}%` : ABSENT;
}

export function formatScore(value: number | null): string {
  return isFiniteNumber(value) ? value.toFixed(2) : ABSENT;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** 在 `levelCount` 个等级之间的 0 起始索引，做了钳制，让古怪的分数也能画出来。 */
function levelOf(score: number, levelCount: number): number {
  return Math.min(Math.max(Math.round(score), 0), levelCount - 1);
}

/** 一个指标属于哪个路由层，用于给卡片和表格列打标签。 */
export type EvalMode = "jev" | "llm";

/** 该模式无法产生的比率，渲染为缺省而不是零。 */
export const ABSENT_RATE = ABSENT;

export interface MetricCard {
  key: string;
  label: string;
  value: string;
  /** 对这个数字统计了什么的一句简短说明，显示在数值下方。 */
  detail: string;
  tone: Tone;
}

export interface ModeCardSet {
  mode: EvalMode;
  label: string;
  cards: MetricCard[];
}

/**
 * 某个模式的汇总卡片。
 *
 * 每个计数都显示在它所占份额的用例总数旁边，因为「88%」看不出那是 50 个里的
 * 44 个还是 5 个里的 4 个。某个模式无法产生的指标——基线没有策略结论——会被
 * 直接略去，而不是显示成零。
 */
export function modeCardSet(metrics: EvalModeMetrics): ModeCardSet {
  const total = metrics.case_count;
  const cards: MetricCard[] = [
    {
      key: "expected",
      label: "期望命中",
      value: formatRate(metrics.expected_match_rate),
      detail: `${metrics.expected_match_count}/${total} 选择了期望动作`,
      tone: rateTone(metrics.expected_match_rate),
    },
    {
      key: "allowed",
      label: "允许集命中",
      value: formatRate(metrics.allowed_match_rate),
      detail: `${metrics.allowed_match_count}/${total} 选择了可接受动作`,
      tone: rateTone(metrics.allowed_match_rate),
    },
    {
      key: "success",
      label: "任务成功",
      value: formatRate(metrics.success_rate),
      // 基线没有策略结论，因此确认不是它能成功的一部分；说出来就是在描述
      // 一个它不可能拥有的事实。
      detail:
        metrics.confirmation_match_count === null
          ? `${metrics.success_count}/${total} 选择了可接受动作`
          : `${metrics.success_count}/${total} 命中且确认结论与用例要求一致`,
      tone: rateTone(metrics.success_rate),
    },
    {
      key: "latency",
      label: "延迟",
      value: formatDuration(metrics.latency.mean_ms),
      detail: `p50 ${formatDuration(metrics.latency.p50_ms)} · p95 ${formatDuration(
        metrics.latency.p95_ms,
      )} · 最大 ${formatDuration(metrics.latency.max_ms)}`,
      tone: "neutral",
    },
    {
      key: "tokens",
      label: "Token",
      value: formatTokens(metrics.input_tokens?.mean ?? null, metrics.output_tokens?.mean ?? null),
      detail:
        metrics.input_tokens === null || metrics.output_tokens === null
          ? "提供方未返回用量"
          : `入 ${metrics.input_tokens.total} · 出 ${metrics.output_tokens.total}，共 ${total} 个用例`,
      tone: "neutral",
    },
  ];

  if (metrics.escalation_rate !== null && metrics.escalation_count !== null) {
    cards.push({
      key: "escalated",
      label: "升级率",
      value: formatRate(metrics.escalation_rate),
      detail: `${metrics.escalation_count}/${total} 中止了自动执行`,
      tone: "neutral",
    });
  }
  if (
    metrics.confirmation_requested_count !== null &&
    metrics.confirmation_match_count !== null
  ) {
    cards.push({
      key: "confirmation",
      label: "确认吻合度",
      value: formatRate(metrics.confirmation_match_count / total),
      detail: `请求确认 ${metrics.confirmation_requested_count} 次 · ${metrics.confirmation_match_count}/${total} 与用例要求一致`,
      tone: rateTone(metrics.confirmation_match_count / total),
    });
  }
  if (metrics.error_count > 0) {
    cards.push({
      key: "errors",
      label: "错误",
      value: formatRate(metrics.error_rate),
      detail: `${metrics.error_count}/${total} 个用例出错`,
      tone: "bad",
    });
  }

  return {
    mode: metrics.mode === "llm" ? "llm" : "jev",
    label: metrics.mode === "llm" ? "LLM 基线" : "Jev",
    cards,
  };
}

/** 一次运行能展示的卡片组，Jev 在前，因为它是主角。 */
export function comparisonCardSets(metrics: EvalComparisonMetrics): ModeCardSet[] {
  const sets: ModeCardSet[] = [];
  if (metrics.jev !== null) {
    sets.push(modeCardSet(metrics.jev));
  }
  if (metrics.llm !== null) {
    sets.push(modeCardSet(metrics.llm));
  }
  return sets;
}

export interface AgreementCard {
  key: "agreement";
  label: string;
  value: string;
  detail: string;
  tone: Tone;
}

/**
 * 两个路由层有多少次选中了同一个动作。除非两边都至少回答了一个用例，否则这个
 * 值是缺省的：「0%」和「从未比较过」是两句不同的话，而只有其中一句是结论。
 */
export function agreementCard(metrics: EvalComparisonMetrics): AgreementCard | null {
  if (metrics.agreement_rate === null || metrics.compared_count === null) {
    return null;
  }
  const compared = metrics.compared_count;
  const agreed = metrics.agreement_count ?? 0;
  return {
    key: "agreement",
    label: "路由一致率",
    value: formatRate(metrics.agreement_rate),
    detail: `${agreed}/${compared} 个可比用例选择了相同动作`,
    tone: rateTone(metrics.agreement_rate),
  };
}

export interface ComparisonRow {
  caseId: string;
  goal: string;
  expectedAction: string;
  jev: EvalCaseOutcome | null;
  llm: EvalCaseOutcome | null;
  agreed: boolean | null;
}

/**
 * 每个用例一行，把两个路由层的结果配成对。
 *
 * 结果按 `(case_id, mode)` 顺序到达，因此一次遍历就能配对。任一侧没有作答时
 * `agreed` 保持 `null`：路由层报错不算分歧，把它算成分歧会低估一致率。
 */
export function comparisonRows(outcomes: EvalCaseOutcome[]): ComparisonRow[] {
  const byCase = new Map<string, { jev?: EvalCaseOutcome; llm?: EvalCaseOutcome }>();
  for (const outcome of outcomes) {
    const entry = byCase.get(outcome.case_id) ?? {};
    if (outcome.mode === "llm") {
      entry.llm = outcome;
    } else {
      entry.jev = outcome;
    }
    byCase.set(outcome.case_id, entry);
  }
  return [...byCase.entries()].map(([caseId, entry]) => {
    const jev = entry.jev ?? null;
    const llm = entry.llm ?? null;
    const agreed =
      jev !== null && llm !== null && jev.action !== null && llm.action !== null
        ? jev.action === llm.action
        : null;
    const reference = jev ?? llm;
    return {
      caseId,
      goal: reference?.goal ?? "",
      expectedAction: reference?.expected_action ?? ABSENT,
      jev,
      llm,
      agreed,
    };
  });
}

/** 路由层上报的动作，或者取代它的那条错误。 */
export function outcomeAction(outcome: EvalCaseOutcome | null): string {
  if (outcome === null) {
    return ABSENT;
  }
  if (outcome.action !== null) {
    return outcome.action;
  }
  return outcome.error === null ? ABSENT : `出错：${outcome.error}`;
}

export function formatRate(value: number | null): string {
  return isFiniteNumber(value) ? `${(value * 100).toFixed(1)}%` : ABSENT;
}

export function formatTokens(input: number | null, output: number | null): string {
  if (!isFiniteNumber(input) || !isFiniteNumber(output)) {
    return ABSENT;
  }
  // 对整数计数取均值：一位小数已经是读者能用上的极限，而原始浮点数打印出来的
  // 是算术过程而不是那个数字。
  return `${round(input)} / ${round(output)}`;
}

function round(value: number): string {
  return (Math.round(value * 10) / 10).toString();
}

/** 比率的色调：越高越好，而且分档刻意做得比较粗。 */
export function rateTone(value: number | null): Tone {
  if (!isFiniteNumber(value)) {
    return "neutral";
  }
  if (value >= 0.9) {
    return "good";
  }
  if (value >= 0.7) {
    return "neutral";
  }
  return "bad";
}
