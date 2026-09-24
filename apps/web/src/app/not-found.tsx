import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <h1 className="text-lg font-semibold tracking-tight text-ink">没有这条运行</h1>
      <p className="text-sm text-ink-2">
        API 不认识这个 task id。运行记录存在于 API 进程的内存中，因此重启之前的 id 将找不到。
      </p>
      <Link href="/" className="text-xs text-ink-2 transition-colors hover:text-ink">
        ← 所有运行
      </Link>
    </div>
  );
}
