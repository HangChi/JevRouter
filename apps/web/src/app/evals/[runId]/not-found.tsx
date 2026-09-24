import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <h1 className="text-lg font-semibold tracking-tight text-ink">No such eval run</h1>
      <p className="text-sm text-ink-2">
        The API does not know this run id. Eval runs live in the API&rsquo;s database, so a run
        recorded against a different database file will not be found.
      </p>
      <Link href="/evals" className="text-xs text-ink-2 transition-colors hover:text-ink">
        ← All eval runs
      </Link>
    </div>
  );
}
