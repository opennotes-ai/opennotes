import { createSignal, Show, type JSX } from "solid-js";
import { useAction } from "@solidjs/router";
import { Input } from "@opennotes/ui/components/ui/input";
import { Button } from "@opennotes/ui/components/ui/button";
import {
  MAX_PDF_LABEL,
  isPdfFile,
  isPdfTooLarge,
} from "~/lib/pdf-constraints";
import {
  requestUploadUrlAction,
  submitPdfAnalysisAction,
} from "~/routes/analyze.data";

export interface PdfUploadProps {
  pending?: boolean;
}

type UploadStep = "idle" | "getting-url" | "uploading" | "analyzing";

const FIELD_SIZE = "h-11 text-base";

const STEP_LABEL: Record<UploadStep, string> = {
  idle: "Upload PDF",
  "getting-url": "Preparing...",
  uploading: "Uploading...",
  analyzing: "Analyzing...",
};

export default function PdfUpload(props: PdfUploadProps): JSX.Element {
  const [selectedPdf, setSelectedPdf] = createSignal<File | null>(null);
  const [error, setError] = createSignal<string | null>(null);
  const [step, setStep] = createSignal<UploadStep>("idle");

  const requestUrl = useAction(requestUploadUrlAction);
  const submitAnalysis = useAction(submitPdfAnalysisAction);

  const isWorking = () => step() !== "idle" || props.pending;

  const handleSubmit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = async (
    event,
  ) => {
    event.preventDefault();

    const file = selectedPdf();
    if (!file) {
      setError("Choose a PDF file to analyze.");
      return;
    }
    if (!isPdfFile(file)) {
      setError("Please choose a PDF file.");
      return;
    }
    if (isPdfTooLarge(file)) {
      setError("PDF must be 50 MB or less.");
      return;
    }
    setError(null);

    try {
      setStep("getting-url");
      const upload = await requestUrl();
      if (!upload || typeof upload !== "object" || !("gcs_key" in upload)) {
        throw new Error("Failed to get upload URL");
      }
      const { gcs_key, upload_url } = upload as {
        gcs_key: string;
        upload_url: string;
      };

      setStep("uploading");
      const { uploadPdfToSignedUrl } = await import("~/lib/pdf-upload");
      await uploadPdfToSignedUrl(upload_url, file);

      setStep("analyzing");
      const fd = new FormData();
      fd.set("gcs_key", gcs_key);
      fd.set("filename", file.name);
      await submitAnalysis(fd);
    } catch (err: unknown) {
      setStep("idle");
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <form
      method="post"
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
          disabled={isWorking()}
        />
        <Button
          type="submit"
          disabled={isWorking()}
          data-testid="vibecheck-pdf-submit"
          class={`${FIELD_SIZE} px-4`}
        >
          {STEP_LABEL[step()] ?? "Upload PDF"}
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
