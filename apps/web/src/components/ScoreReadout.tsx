import type { ScoreReadout as Readout } from "@/lib/viewModel";
import { formatScore } from "@/lib/viewModel";

const LEVEL_FILL = ["bg-level-1", "bg-level-2", "bg-level-3", "bg-level-4", "bg-level-5"];

/**
 * A provider score, which the core package does not normalize.
 *
 * The number is the primary read; the pip strip is an ordered ordinal ramp
 * over the levels the question was asked against, and the threshold — when one
 * exists — is stated in words rather than implied by colour.
 */
export function ScoreReadout({ readout }: { readout: Readout }) {
  const pips = Array.from({ length: readout.levelCount }, (_, index) => index);

  return (
    <div className="grid grid-cols-[minmax(7rem,10rem)_1fr_auto] items-center gap-3">
      <span className="text-xs text-ink-2">{readout.label}</span>
      <span className="flex items-center gap-0.5" aria-hidden="true">
        {pips.map((index) => (
          <span
            key={index}
            className={`h-2 w-2 rounded-[2px] ${
              index <= readout.level ? LEVEL_FILL[index] : "bg-hairline"
            }`}
          />
        ))}
      </span>
      <span className="font-mono text-xs tabular-nums text-ink">
        {formatScore(readout.value)}
        <span
          className="ml-2 text-muted"
          title="核心包不对该分数做归一化，因此这里标注刻度范围而不是假定。"
        >
          scale 0–{readout.levelCount - 1}
        </span>
      </span>
    </div>
  );
}
