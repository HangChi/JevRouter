import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <h1 className="text-lg font-semibold tracking-tight text-ink">No such run</h1>
      <p className="text-sm text-ink-2">
        The API does not know this task id. Runs live in the API process&rsquo;s memory, so an id from
        before a restart will not be found.
      </p>
      <Link href="/" className="text-xs text-ink-2 transition-colors hover:text-ink">
        ← All runs
      </Link>
    </div>
  );
}
