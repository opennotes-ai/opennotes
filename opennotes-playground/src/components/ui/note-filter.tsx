import { For, Show, createSignal } from "solid-js";
import { cn } from "~/lib/cn";

type FilterGroup = {
  label: string;
  key: string;
  options: { value: string; label: string }[];
};

const FILTER_GROUPS: FilterGroup[] = [
  {
    label: "Classification",
    key: "classification",
    options: [
      { value: "NOT_MISLEADING", label: "Not Misleading" },
      { value: "MISINFORMED_OR_POTENTIALLY_MISLEADING", label: "Misinformed / Potentially Misleading" },
    ],
  },
  {
    label: "Status",
    key: "status",
    options: [
      { value: "CURRENTLY_RATED_HELPFUL", label: "Currently Rated Helpful" },
      { value: "CURRENTLY_RATED_NOT_HELPFUL", label: "Currently Rated Not Helpful" },
      { value: "NEEDS_MORE_RATINGS", label: "Needs More Ratings" },
    ],
  },
];

export type NoteFilterValues = {
  classification: string[];
  status: string[];
};

export default function NoteFilter(props: {
  classification: string[];
  status: string[];
  onChange: (values: NoteFilterValues) => void;
}) {
  const [open, setOpen] = createSignal(false);

  const activeCount = () => props.classification.length + props.status.length;

  function toggle(group: string, value: string) {
    const current = group === "classification" ? [...props.classification] : [...props.status];
    const idx = current.indexOf(value);
    if (idx >= 0) {
      current.splice(idx, 1);
    } else {
      current.push(value);
    }
    props.onChange({
      classification: group === "classification" ? current : props.classification,
      status: group === "status" ? current : props.status,
    });
  }

  function clearAll() {
    props.onChange({ classification: [], status: [] });
  }

  function isChecked(group: string, value: string): boolean {
    const list = group === "classification" ? props.classification : props.status;
    return list.includes(value);
  }

  return (
    <div class="relative">
      <button
        data-testid="note-filter-toggle"
        class={cn(
          "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
          activeCount() > 0
            ? "border-primary bg-primary/10 text-primary"
            : "border-input hover:bg-muted",
        )}
        onClick={() => setOpen(!open())}
        aria-expanded={open()}
      >
        Filter
        <Show when={activeCount() > 0}>
          <span class="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
            {activeCount()}
          </span>
        </Show>
      </button>

      <Show when={open()}>
        <div
          data-testid="note-filter-panel"
          class="absolute right-0 top-full z-10 mt-1 w-72 rounded-lg border border-border bg-card p-3 shadow-lg"
        >
          <div class="mb-2 flex items-center justify-between">
            <span class="text-xs font-semibold text-muted-foreground">Filters</span>
            <Show when={activeCount() > 0}>
              <button
                class="text-xs text-primary hover:underline"
                onClick={clearAll}
              >
                Clear all
              </button>
            </Show>
          </div>

          <For each={FILTER_GROUPS}>
            {(group) => (
              <div class="mt-2">
                <div class="mb-1 text-xs font-medium text-muted-foreground">{group.label}</div>
                <For each={group.options}>
                  {(option) => (
                    <label class="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted/50">
                      <input
                        type="checkbox"
                        data-testid={`filter-${group.key}-${option.value}`}
                        checked={isChecked(group.key, option.value)}
                        onChange={() => toggle(group.key, option.value)}
                        class="h-3.5 w-3.5 rounded border-input"
                      />
                      {option.label}
                    </label>
                  )}
                </For>
              </div>
            )}
          </For>
        </div>
      </Show>
    </div>
  );
}
