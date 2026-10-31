import type { ProbabilityMeter as Meter } from "@/lib/viewModel";
import { formatProbability } from "@/lib/viewModel";

/**
 * 一个 0–1 的概率与它阈值的对照。
 *
 * 填充色承载严重程度：信号还在自己的区间内时用强调色，一旦跨到策略引擎会据此
 * 行动的那一侧就换成警告色。轨道是同色阶更浅的一档，让状态贯穿整条进度条；数值
 * 始终印在刻度标记旁边——刻度标记从不是读取数字的唯一途径。
 */
export function ProbabilityMeter({ meter }: { meter: Meter }) {
  const fill = meter.crossed ? "bg-warning" : "bg-accent";
  const width = `${Math.min(Math.max(meter.value, 0), 1) * 100}%`;
  const comparison = meter.direction === "above" ? "above" : "below";

  return (
    <div className="grid grid-cols-[minmax(7rem,10rem)_1fr_auto] items-center gap-3">
      <span className="text-xs text-ink-2">{meter.label}</span>
      <span className="relative block h-2 rounded-sm bg-accent-track">
        <span
          className={`absolute inset-y-0 left-0 rounded-r-[4px] ${fill}`}
          style={{ width }}
          aria-hidden="true"
        />
        <span
          className="absolute -top-1 -bottom-1 w-0.5 bg-muted"
          style={{ left: `${meter.threshold * 100}%` }}
          aria-hidden="true"
        />
      </span>
      <span className="font-mono text-xs tabular-nums text-ink">
        {formatProbability(meter.value)}
        <span className="ml-2 text-muted">
          {comparison} {meter.threshold.toFixed(2)}
        </span>
      </span>
    </div>
  );
}
