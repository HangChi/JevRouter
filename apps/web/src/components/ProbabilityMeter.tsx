import type { ProbabilityMeter as Meter } from "@/lib/viewModel";
import { formatProbability } from "@/lib/viewModel";

/**
 * One 0–1 probability against its threshold.
 *
 * The fill carries severity: the accent hue while the signal is inside its
 * band, the warning hue once it has crossed into the side the Policy Engine
 * acts on. The track is a lighter step of the same ramp so the state reads
 * across the whole bar, and the value is always printed beside the mark — the
 * mark is never the only way to read the number.
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
