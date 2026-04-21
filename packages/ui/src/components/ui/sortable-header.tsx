import type { Component } from "solid-js";

type SortDirection = "asc" | "desc" | null;

interface SortableHeaderProps {
  label: string;
  sortKey: string;
  activeSort: { key: string; direction: SortDirection };
  onSort: (key: string, direction: SortDirection) => void;
  class?: string;
}

function SortIcon(props: { direction: SortDirection; active: boolean }) {
  if (!props.active || !props.direction) {
    return (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ml-0.5 inline size-3.5 text-muted-foreground">
        <path d="M7 15l5 5l5 -5" />
        <path d="M7 9l5 -5l5 5" />
      </svg>
    );
  }
  if (props.direction === "desc") {
    return (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ml-0.5 inline size-3.5 text-foreground">
        <path d="M6 15l6 6l6 -6" />
      </svg>
    );
  }
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ml-0.5 inline size-3.5 text-foreground">
      <path d="M6 9l6 -6l6 6" />
    </svg>
  );
}

const SortableHeader: Component<SortableHeaderProps> = (props) => {
  const isActive = () => props.activeSort.key === props.sortKey;
  const direction = () => (isActive() ? props.activeSort.direction : null);

  const handleClick = () => {
    const nextDir =
      direction() === null ? "desc" : direction() === "desc" ? "asc" : null;
    props.onSort(props.sortKey, nextDir);
  };

  return (
    <th
      class={
        "cursor-pointer select-none hover:bg-muted/50 " + (props.class ?? "")
      }
      data-sortable="true"
      data-sort-active={isActive() && !!direction()}
      data-sort-direction={direction() ?? undefined}
      onClick={handleClick}
    >
      {props.label}
      <SortIcon direction={direction()} active={isActive()} />
    </th>
  );
};

export default SortableHeader;
export type { SortDirection };
