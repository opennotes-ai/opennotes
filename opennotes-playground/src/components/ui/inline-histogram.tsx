import { For } from "solid-js";
import { humanizeLabel } from "~/lib/format";

export const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export default function InlineHistogram(props: { data: Record<string, number> }) {
  const entries = () => Object.entries(props.data);
  const max = () => Math.max(...entries().map(([, v]) => v), 1);

  return (
    <div class="flex flex-col gap-0.5 min-w-[100px]">
      <For each={entries()}>
        {([label, count], i) => (
          <div class="flex items-center gap-1 text-xs">
            <span
              class="w-[60px] truncate text-muted-foreground"
              title={humanizeLabel(label)}
            >
              {humanizeLabel(label)}
            </span>
            <div class="flex-1 h-2.5 rounded-sm bg-muted overflow-hidden">
              <div
                class="h-full rounded-sm"
                style={{
                  width: `${(count / max()) * 100}%`,
                  "background-color": CHART_COLORS[i() % CHART_COLORS.length],
                }}
              />
            </div>
            <span class="w-4 text-right tabular-nums text-muted-foreground">
              {count}
            </span>
          </div>
        )}
      </For>
    </div>
  );
}
