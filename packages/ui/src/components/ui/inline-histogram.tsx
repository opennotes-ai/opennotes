import { For, createMemo } from "solid-js";
import { SEMANTIC_COLORS, getSemanticColor } from "../../palettes/chart-colors";

// Generic fallback palette for unknown keys. Distinct from SEMANTIC_COLORS
// (in palettes/chart-colors.ts) which maps domain-specific enum values
// (HELPFUL, NOT_MISLEADING, WRITE_NOTE, ...) to fixed hex colors. When a
// key has no semantic mapping we round-robin through these theme CSS vars
// so bars still get distinct, theme-aware colors.
export const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

function defaultFormatLabel(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export type InlineHistogramProps = {
  data: Record<string, number>;
  /**
   * Optional label formatter for histogram keys. Consumers with domain-aware
   * formatters (e.g., Community Notes rating enums) should pass their own;
   * otherwise a generic snake_case/UPPER_CASE → Title Case transform is used.
   */
  formatLabel?: (raw: string) => string;
};

export { SEMANTIC_COLORS };

export default function InlineHistogram(props: InlineHistogramProps) {
  const entries = createMemo(() => Object.entries(props.data));
  const max = createMemo(() => Math.max(...entries().map(([, v]) => v), 1));
  const format = (raw: string) => (props.formatLabel ?? defaultFormatLabel)(raw);

  return (
    <div class="flex flex-col gap-0.5 min-w-[100px]">
      <For each={entries()}>
        {([label, count], i) => (
          <div class="flex items-center gap-1 text-xs">
            <span
              class="w-[60px] truncate text-muted-foreground"
              title={format(label)}
            >
              {format(label)}
            </span>
            <div class="flex-1 h-2.5 rounded-sm bg-muted overflow-hidden">
              <div
                class="h-full rounded-sm"
                style={{
                  width: `${(count / max()) * 100}%`,
                  "background-color": getSemanticColor(label) ?? CHART_COLORS[i() % CHART_COLORS.length],
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
