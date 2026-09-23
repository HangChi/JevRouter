import { statusTone, type Tone } from "@/lib/viewModel";

const TONE_DOT: Record<Tone, string> = {
  neutral: "bg-muted",
  live: "bg-accent",
  blocked: "bg-warning",
  good: "bg-good",
  bad: "bg-critical",
};

const TONE_TINT: Record<Tone, string> = {
  neutral: "bg-muted/10",
  live: "bg-accent/10",
  blocked: "bg-warning/15",
  good: "bg-good/10",
  bad: "bg-critical/10",
};

/**
 * A status is never carried by colour alone: the dot tints the pill and the
 * transported status string is always spelled out beside it.
 */
export function StatusBadge({ status }: { status: string }) {
  const tone = statusTone(status);
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-hairline px-2.5 py-1 text-xs font-medium tracking-wide text-ink ${TONE_TINT[tone]}`}
    >
      <span className={`h-2 w-2 rounded-full ${TONE_DOT[tone]}`} aria-hidden="true" />
      {status.replace(/_/g, " ")}
    </span>
  );
}
