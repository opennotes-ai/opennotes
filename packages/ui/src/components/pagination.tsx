import { A } from "@solidjs/router";
import { Show } from "solid-js";
import { Button } from "./ui/button";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
}

export default function Pagination(props: PaginationProps) {
  const hasPrev = () => props.currentPage > 1;
  const hasNext = () => props.currentPage < props.totalPages;

  return (
    <nav aria-label="Pagination" class="mt-6 flex items-center gap-3">
      <Show
        when={hasPrev()}
        fallback={
          <Button variant="outline" size="sm" disabled aria-disabled="true">
            Previous
          </Button>
        }
      >
        <Button variant="outline" size="sm" as={A} href={`/?page=${props.currentPage - 1}`}>
          Previous
        </Button>
      </Show>
      <span class="text-sm text-muted-foreground">
        Page {props.currentPage} of {props.totalPages}
      </span>
      <Show
        when={hasNext()}
        fallback={
          <Button variant="outline" size="sm" disabled aria-disabled="true">
            Next
          </Button>
        }
      >
        <Button variant="outline" size="sm" as={A} href={`/?page=${props.currentPage + 1}`}>
          Next
        </Button>
      </Show>
    </nav>
  );
}
