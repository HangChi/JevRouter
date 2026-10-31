import type { ScoreReadout as Readout } from "@/lib/viewModel";
import { formatScore } from "@/lib/viewModel";

const LEVEL_FILL = ["bg-level-1", "bg-level-2", "bg-level-3", "bg-level-4", "bg-level-5"];

/**
 * 一个提供方分数，核心包不对它做归一化。
 *
 * 数字是主要的读法；刻度点条是针对提问时所依据的等级、按序排列的等级阶梯；
 * 阈值——如果存在——用文字说明，而不是靠颜色暗示。
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
