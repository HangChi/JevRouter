import type { Metadata } from "next";
import Link from "next/link";

import { resolveUpstream } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  title: "JevRouter 仪表盘",
  description: "JevRouter agent 核心的运行、路由决策与步骤 trace。",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const upstream = resolveUpstream(process.env);

  return (
    <html lang="zh-CN">
      <body className="flex min-h-screen flex-col bg-page font-sans text-ink antialiased">
        <header className="border-b border-hairline bg-surface">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
            <Link href="/" className="text-sm font-semibold tracking-tight text-ink">
              JevRouter
            </Link>
            <span className="text-xs text-muted">运行与评测仪表盘</span>
            <nav className="ml-auto flex items-center gap-3 text-xs">
              <Link href="/" className="text-ink-2 transition-colors hover:text-ink">
                运行
              </Link>
              <Link href="/evals" className="text-ink-2 transition-colors hover:text-ink">
                评测
              </Link>
              <Link href="/policy" className="text-ink-2 transition-colors hover:text-ink">
                策略
              </Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>

        <footer className="border-t border-hairline bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-3 text-xs text-muted">
            正在读取 <span className="font-mono text-ink-2">{upstream}</span> 的 API。提供方凭证只存在于
            API 进程中，永远不会发送到这个页面。
          </div>
        </footer>
      </body>
    </html>
  );
}
