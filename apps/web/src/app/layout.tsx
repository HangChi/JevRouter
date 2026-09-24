import type { Metadata } from "next";
import Link from "next/link";

import { resolveUpstream } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  title: "JevRouter trace dashboard",
  description: "Runs, routing decisions and step traces from the JevRouter agent core.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const upstream = resolveUpstream(process.env);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col bg-page font-sans text-ink antialiased">
        <header className="border-b border-hairline bg-surface">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
            <Link href="/" className="text-sm font-semibold tracking-tight text-ink">
              JevRouter
            </Link>
            <span className="text-xs text-muted">trace dashboard</span>
            <nav className="ml-auto flex items-center gap-3 text-xs">
              <Link href="/" className="text-ink-2 transition-colors hover:text-ink">
                Runs
              </Link>
              <Link href="/evals" className="text-ink-2 transition-colors hover:text-ink">
                Evals
              </Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>

        <footer className="border-t border-hairline bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-3 text-xs text-muted">
            Reading the API at <span className="font-mono text-ink-2">{upstream}</span>. The provider
            credential stays in the API process and is never sent to this page.
          </div>
        </footer>
      </body>
    </html>
  );
}
