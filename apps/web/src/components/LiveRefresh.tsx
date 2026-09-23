"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Keeps a live run current.
 *
 * The API has no streaming endpoint, so the page re-renders on an interval
 * instead of holding a connection open. Polling stops as soon as the run is
 * terminal: a finished run costs no further requests, and the server components
 * re-run on their own when a prompt is answered.
 */
export function LiveRefresh({ active, intervalMs = 2000 }: { active: boolean; intervalMs?: number }) {
  const router = useRouter();

  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = setInterval(() => {
      router.refresh();
    }, intervalMs);
    return () => {
      clearInterval(timer);
    };
  }, [active, intervalMs, router]);

  if (!active) {
    return null;
  }

  return (
    <span className="inline-flex items-center gap-2 text-xs text-muted">
      <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
      refreshing every {intervalMs / 1000}s
    </span>
  );
}
