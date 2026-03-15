import { Show } from "solid-js";
import { Button } from "~/components/ui/button";

interface PaginationControlsProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  label?: string;
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
}

export default function PaginationControls(props: PaginationControlsProps) {
  const hasPrev = () => props.currentPage > 1;
  const hasNext = () => props.currentPage < props.totalPages;

  return (
    <nav aria-label={props.label ?? "Pagination"} class="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
      <div class="flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          disabled={!hasPrev()}
          onClick={() => props.onPageChange(props.currentPage - 1)}
        >
          Previous
        </Button>
        <span class="text-sm text-muted-foreground">
          Page {props.currentPage} of {props.totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasNext()}
          onClick={() => props.onPageChange(props.currentPage + 1)}
        >
          Next
        </Button>
      </div>
      <Show when={props.onPageSizeChange && props.pageSizeOptions}>
        <div class="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Show</span>
          <select
            data-testid="page-size-selector"
            class="rounded border border-border bg-background px-2 py-1 text-sm"
            value={props.pageSize}
            onChange={(e) => props.onPageSizeChange!(Number(e.currentTarget.value))}
          >
            {props.pageSizeOptions!.map((opt) => (
              <option value={opt}>{opt}</option>
            ))}
          </select>
          <span>per page</span>
        </div>
      </Show>
    </nav>
  );
}
