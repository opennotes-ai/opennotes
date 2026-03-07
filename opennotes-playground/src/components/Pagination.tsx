import { A } from "@solidjs/router";
import { Show } from "solid-js";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
}

export default function Pagination(props: PaginationProps) {
  const hasPrev = () => props.currentPage > 1;
  const hasNext = () => props.currentPage < props.totalPages;

  return (
    <nav aria-label="Pagination" style={{ display: "flex", gap: "1rem", "align-items": "center", "margin-top": "2rem" }}>
      <Show when={hasPrev()} fallback={<span aria-disabled="true">Previous</span>}>
        <A href={`/simulations?page=${props.currentPage - 1}`}>Previous</A>
      </Show>
      <span>
        Page {props.currentPage} of {props.totalPages}
      </span>
      <Show when={hasNext()} fallback={<span aria-disabled="true">Next</span>}>
        <A href={`/simulations?page=${props.currentPage + 1}`}>Next</A>
      </Show>
    </nav>
  );
}
