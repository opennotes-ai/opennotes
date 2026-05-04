import { createSignal, Show, type JSX } from "solid-js";
import { Input } from "@opennotes/ui/components/ui/input";
import { Button } from "@opennotes/ui/components/ui/button";
import {
  MAX_PDF_LABEL,
  isPdfFile,
  isPdfTooLarge,
} from "~/lib/pdf-constraints";

export interface PdfUploadProps {
  action: unknown;
  pending?: boolean;
}

const FIELD_SIZE = "h-11 text-base";

export default function PdfUpload(props: PdfUploadProps): JSX.Element {
  const [selectedPdf, setSelectedPdf] = createSignal<File | null>(null);
  const [error, setError] = createSignal<string | null>(null);

  const handleSubmit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = (
    event,
  ) => {
    const file = selectedPdf();
    if (!file) {
      event.preventDefault();
      setError("Choose a PDF file to analyze.");
      return;
    }
    if (!isPdfFile(file)) {
      event.preventDefault();
      setError("Please choose a PDF file.");
      return;
    }
    if (isPdfTooLarge(file)) {
      event.preventDefault();
      setError("PDF must be 50 MB or less.");
      return;
    }
    setError(null);
  };

  return (
    <form
      action={props.action as string | undefined}
      method="post"
      enctype="multipart/form-data"
      onSubmit={handleSubmit}
      class="mx-auto flex w-full max-w-xl flex-col gap-3"
      novalidate
    >
      <label for="vibecheck-pdf" class="sr-only">
        PDF to analyze
      </label>
      <div class="flex flex-col gap-2 sm:flex-row">
        <Input
          id="vibecheck-pdf"
          name="pdf"
          type="file"
          accept=".pdf,application/pdf"
          data-testid="vibecheck-pdf-input"
          onChange={(event) => {
            const next = event.currentTarget.files?.[0] ?? null;
            setSelectedPdf(next);
            if (error()) setError(null);
          }}
          aria-invalid={error() ? "true" : undefined}
          aria-describedby={error() ? "vibecheck-pdf-error" : undefined}
          class={`${FIELD_SIZE} cursor-pointer px-4 shadow-xs`}
          disabled={props.pending}
        />
        <Button
          type="submit"
          disabled={props.pending}
          class={`${FIELD_SIZE} px-4`}
        >
          {props.pending ? "Uploading..." : "Upload PDF"}
        </Button>
      </div>
      <p class="text-xs text-muted-foreground" data-testid="pdf-upload-copy">
        Upload a PDF for analysis. PDFs up to {MAX_PDF_LABEL}.
      </p>
      <Show when={error()}>
        {(message) => (
          <p
            id="vibecheck-pdf-error"
            role="alert"
            class="text-sm text-destructive"
          >
            {message()}
          </p>
        )}
      </Show>
    </form>
  );
}
