/**
 * Raw JSON from a trace field, collapsed until it is wanted.
 *
 * Tool results, arguments and state snapshots have a shape this layer does not
 * model, so they are shown verbatim rather than through a fixed view.
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
