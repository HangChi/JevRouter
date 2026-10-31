import type { Tone } from "@/lib/viewModel";

const TONE_BOX: Record<Tone, string> = {
  neutral: "border-hairline bg-page text-ink-2",
  live: "border-accent/40 bg-accent/10 text-ink",
  blocked: "border-warning/50 bg-warning/15 text-ink",
  good: "border-good/40 bg-good/10 text-ink",
  bad: "border-critical/40 bg-critical/10 text-ink",
};

/**
 * 一条运维者必须在读数据之前看到的消息：API 无法连接、运行带有诊断信息，或者
 * 回答来得太晚。连接失败会点名上游地址，让配置错误的仪表盘一眼可见，而不是
 * 看起来像一个空系统。
 */
export function Notice({
  tone = "neutral",
  title,
  children,
}: {
  tone?: Tone;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${TONE_BOX[tone]}`} role="status">
      <p className="font-medium">{title}</p>
      {children === undefined ? null : <div className="mt-1 text-xs">{children}</div>}
    </div>
  );
}
