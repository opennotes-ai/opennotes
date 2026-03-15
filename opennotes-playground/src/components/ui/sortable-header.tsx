import type { Component } from "solid-js";

type SortDirection = "asc" | "desc" | null;

interface SortableHeaderProps {
  label: string;
  sortKey: string;
  activeSort: { key: string; direction: SortDirection };
  onSort: (key: string, direction: SortDirection) => void;
  class?: string;
}

const SortableHeader: Component<SortableHeaderProps> = (props) => {
  const isActive = () => props.activeSort.key === props.sortKey;
  const direction = () => (isActive() ? props.activeSort.direction : null);

  const handleClick = () => {
    const nextDir =
      direction() === null ? "desc" : direction() === "desc" ? "asc" : null;
    props.onSort(props.sortKey, nextDir);
  };

  const arrow = () => {
    if (!isActive() || !direction()) return "\u2195";
    return direction() === "desc" ? "\u2193" : "\u2191";
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
      {props.label}{" "}
      <span class="ml-0.5 text-muted-foreground">{arrow()}</span>
    </th>
  );
};

export default SortableHeader;
export type { SortDirection };
