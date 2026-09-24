import type { Tone } from "@/lib/viewModel";

const TONE_BOX: Record<Tone, string> = {
  neutral: "border-hairline bg-surface text-ink",
  live: "border-accent/40 bg-accent/10 text-ink",
  blocked: "border-warning/50 bg-warning/15 text-ink",
  good: "border-good/40 bg-good/10 text-ink",
  bad: "border-critical/40 bg-critical/10 text-ink",
};

/**
 * One aggregate number. The count that produced the rate is always shown under
 * it, because "88%" hides whether that is 44 of 50 or 4 of 5 — and a calibration
 * decision is made on the count, not the percentage.
 */
export function MetricCard({ card }: { card: import("@/lib/viewModel").MetricCard }) {
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${TONE_BOX[card.tone]}`}>
      <p className="text-[0.65rem] font-semibold tracking-widest text-muted uppercase">
        {card.label}
      </p>
      <p className="mt-1 font-mono text-lg tabular-nums">{card.value}</p>
      <p className="mt-0.5 text-xs text-ink-2">{card.detail}</p>
    </div>
  );
}
