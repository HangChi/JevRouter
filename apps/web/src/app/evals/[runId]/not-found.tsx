import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <h1 className="text-lg font-semibold tracking-tight text-ink">没有这条评测运行</h1>
      <p className="text-sm text-ink-2">
        API 不认识这个 run id。评测运行记录在 API 的数据库中，因此记到别的数据库文件里的运行将找不到。
      </p>
      <Link href="/evals" className="text-xs text-ink-2 transition-colors hover:text-ink">
        ← 所有评测运行
      </Link>
    </div>
  );
}
