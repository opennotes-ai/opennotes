import { For, Show } from "solid-js";
import { cn } from "~/lib/cn";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuGroupLabel,
  DropdownMenuSeparator,
  DropdownMenuCheckboxItem,
} from "~/components/ui/dropdown-menu";

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
    <DropdownMenu>
      <DropdownMenuTrigger
        data-testid="note-filter-toggle"
        class={cn(
          "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
          activeCount() > 0
            ? "border-primary bg-primary/10 text-primary"
            : "border-input hover:bg-muted",
        )}
      >
        Filter
        <Show when={activeCount() > 0}>
          <span class="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
            {activeCount()}
          </span>
        </Show>
      </DropdownMenuTrigger>
      <DropdownMenuContent class="w-72" data-testid="note-filter-panel">
        <div class="mb-1 flex items-center justify-between px-2 py-1">
          <span class="text-xs font-semibold text-muted-foreground">Filters</span>
          <Show when={activeCount() > 0}>
            <button class="text-xs text-primary hover:underline" onClick={clearAll}>
              Clear all
            </button>
          </Show>
        </div>
        <For each={FILTER_GROUPS}>
          {(group, i) => (
            <>
              <Show when={i() > 0}>
                <DropdownMenuSeparator />
              </Show>
              <DropdownMenuGroup>
                <DropdownMenuGroupLabel>{group.label}</DropdownMenuGroupLabel>
                <For each={group.options}>
                  {(option) => (
                    <DropdownMenuCheckboxItem
                      data-testid={`filter-${group.key}-${option.value}`}
                      checked={isChecked(group.key, option.value)}
                      onChange={() => toggle(group.key, option.value)}
                      closeOnSelect={false}
                    >
                      {option.label}
                    </DropdownMenuCheckboxItem>
                  )}
                </For>
              </DropdownMenuGroup>
            </>
          )}
        </For>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
