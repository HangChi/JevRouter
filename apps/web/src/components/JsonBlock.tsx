/**
 * trace 字段里的原始 JSON，默认折叠，需要时再展开。
 *
 * 工具结果、参数和状态快照的形状这一层并不建模，因此原样展示，而不套用一个
 * 固定的视图。
 */
export function JsonBlock({
  label,
  value,
  defaultOpen = false,
}: {
  label: string;
  value: unknown;
  defaultOpen?: boolean;
}) {
  const text = JSON.stringify(value, null, 2);

  return (
    <details
      open={defaultOpen}
      className="rounded-md border border-hairline bg-page px-3 py-2"
    >
      <summary className="cursor-pointer text-xs font-medium text-ink-2 select-none">
        {label}
      </summary>
      <pre className="mt-2 overflow-x-auto font-mono text-xs leading-relaxed text-ink">
        {text ?? "null"}
      </pre>
    </details>
  );
}
