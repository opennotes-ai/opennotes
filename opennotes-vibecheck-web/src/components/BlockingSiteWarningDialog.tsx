import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@opennotes/ui";
import { Button } from "@opennotes/ui/components/ui/button";
import type { JSX } from "solid-js";

export interface BlockingSiteWarningDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  url: string;
  hostFamily: "reddit" | "linkedin";
  onProceedAnyway: () => void;
  onChoosePdf: () => void;
  onChooseScreenshot: () => void;
  onCancel: () => void;
}

export function BlockingSiteWarningDialog(
  props: BlockingSiteWarningDialogProps,
): JSX.Element {
  let proceedButtonRef: HTMLButtonElement | undefined;

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          proceedButtonRef?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>We can’t access this site reliably</DialogTitle>
          <DialogDescription>
            this site usually blocks third-party access, we recommend you upload
            screenshots or a PDF printout of the page until our browser extension
            is ready.
          </DialogDescription>
        </DialogHeader>
        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:space-x-2">
          <Button
            ref={proceedButtonRef}
            type="button"
            onClick={props.onProceedAnyway}
          >
            Try accessing it anyways
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={props.onChoosePdf}
          >
            PDF
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={props.onChooseScreenshot}
          >
            Screenshot
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={props.onCancel}
          >
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
