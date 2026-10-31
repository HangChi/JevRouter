import { statusLabel, statusTone, type Tone } from "@/lib/viewModel";

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
 * 状态绝不只靠颜色传达：圆点为胶囊染色，而传输来的状态字符串始终在它旁边写出来。
 */
export function StatusBadge({ status }: { status: string }) {
  const tone = statusTone(status);
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-hairline px-2.5 py-1 text-xs font-medium tracking-wide text-ink ${TONE_TINT[tone]}`}
    >
      <span className={`h-2 w-2 rounded-full ${TONE_DOT[tone]}`} aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}
