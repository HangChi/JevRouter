import { MetricCard } from "./MetricCard";
import type { ModeCardSet } from "@/lib/viewModel";

/** 一个模式的汇总卡片，以它们所属的路由层作为标题。 */
export function MetricCards({ set }: { set: ModeCardSet }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[0.7rem] font-semibold tracking-widest text-muted uppercase">{set.label}</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {set.cards.map((card) => (
          <MetricCard key={card.key} card={card} />
        ))}
      </div>
    </section>
  );
}
