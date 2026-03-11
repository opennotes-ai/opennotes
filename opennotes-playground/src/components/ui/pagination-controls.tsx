import { Button } from "~/components/ui/button";

interface PaginationControlsProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export default function PaginationControls(props: PaginationControlsProps) {
  const hasPrev = () => props.currentPage > 1;
  const hasNext = () => props.currentPage < props.totalPages;

  return (
    <nav aria-label="Pagination" class="mt-4 flex items-center justify-center gap-3">
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
    </nav>
  );
}
