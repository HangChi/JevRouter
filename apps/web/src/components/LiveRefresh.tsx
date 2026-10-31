"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * 让进行中的运行保持最新。
 *
 * API 没有流式端点，因此页面按固定间隔重新渲染，而不是一直挂着一个连接。运行
 * 一旦进入终态就停止轮询：已结束的运行不再产生额外请求，而用户回答提示后，
 * 服务端组件会自行重新执行。
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
      每 {intervalMs / 1000} 秒刷新
    </span>
  );
}
