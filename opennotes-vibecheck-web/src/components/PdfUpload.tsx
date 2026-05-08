import { createSignal, Show, type JSX } from "solid-js";
import { useAction } from "@solidjs/router";
import { Input } from "@opennotes/ui/components/ui/input";
import { Button } from "@opennotes/ui/components/ui/button";
import {
  MAX_IMAGE_BATCH_LABEL,
  MAX_IMAGE_COUNT,
  MAX_PDF_LABEL,
  imageBatchBytes,
  isImageBatchTooLarge,
  isImageFile,
  isPdfFile,
  isPdfTooLarge,
} from "~/lib/pdf-constraints";
import {
  requestImageUploadUrlsAction,
  requestUploadUrlAction,
  submitImageAnalysisAction,
  submitPdfAnalysisAction,
} from "~/routes/analyze.data";

export interface PdfUploadProps {
  pending?: boolean;
}

type UploadStep = "idle" | "getting-url" | "uploading" | "analyzing" | "converting";

const FIELD_SIZE = "h-11 text-base";

const STEP_LABEL: Record<UploadStep, string> = {
  idle: "Upload",
  "getting-url": "Preparing upload",
  uploading: "Uploading...",
  analyzing: "Analyzing...",
  converting: "Converting images...",
};

function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function PdfUpload(props: PdfUploadProps): JSX.Element {
  const [selectedFiles, setSelectedFiles] = createSignal<File[]>([]);
  const [error, setError] = createSignal<string | null>(null);
  const [step, setStep] = createSignal<UploadStep>("idle");

  const requestUrl = useAction(requestUploadUrlAction);
  const requestImageUrls = useAction(requestImageUploadUrlsAction);
  const submitAnalysis = useAction(submitPdfAnalysisAction);
  const submitImageAnalysis = useAction(submitImageAnalysisAction);

  const isWorking = () => step() !== "idle" || props.pending;

  const handleSubmit: JSX.EventHandler<HTMLFormElement, SubmitEvent> = async (
    event,
  ) => {
    event.preventDefault();

    const files = selectedFiles();
    if (files.length === 0) {
      setError("Choose a PDF or image files to analyze.");
      return;
    }
    const pdfFiles = files.filter(isPdfFile);
    const imageFiles = files.filter(isImageFile);
    if (pdfFiles.length === 1 && files.length === 1) {
      const file = pdfFiles[0];
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
      return;
    }
    if (pdfFiles.length > 0) {
      setError("Choose one PDF or image files, not both.");
      return;
    }
    if (imageFiles.length !== files.length) {
      setError("That image type is not supported.");
      return;
    }
    if (imageFiles.length > MAX_IMAGE_COUNT) {
      setError(`Choose ${MAX_IMAGE_COUNT} images or fewer.`);
      return;
    }
    if (isImageBatchTooLarge(imageFiles)) {
      setError(`Images must total ${MAX_IMAGE_BATCH_LABEL} or less.`);
      return;
    }
    setError(null);

    try {
      setStep("getting-url");
      const upload = await requestImageUrls(
        imageFiles.map((file) => ({
          filename: file.name,
          content_type: file.type,
          size_bytes: file.size,
        })),
      );
      if (!upload || typeof upload !== "object" || !("job_id" in upload)) {
        throw new Error("Failed to get image upload URLs");
      }
      const imageUploads = (upload as {
        job_id: string;
        images: { ordinal: number; upload_url: string }[];
      }).images;

      setStep("uploading");
      const { uploadFileToSignedUrl } = await import("~/lib/pdf-upload");
      for (const image of imageUploads) {
        const file = imageFiles[image.ordinal];
        await uploadFileToSignedUrl(image.upload_url, file, file.type);
      }

      setStep("converting");
      const fd = new FormData();
      fd.set("job_id", (upload as { job_id: string }).job_id);
      fd.set("filename", imageFiles[0]?.name ?? "images");
      await submitImageAnalysis(fd);
    } catch (err: unknown) {
      setStep("idle");
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Something went wrong. Please try again.");
      }
    }
  };

  const selectionCopy = () => {
    const files = selectedFiles();
    if (files.length === 0) return null;
    if (files.length === 1 && isPdfFile(files[0])) return files[0].name;
    return `${files.length} images selected - ${formatBytes(imageBatchBytes(files))}`;
  };

  return (
    <form
      method="post"
      onSubmit={handleSubmit}
      class="mx-auto flex w-full max-w-xl flex-col gap-3"
      novalidate
    >
      <label for="vibecheck-pdf" class="sr-only">
        PDF or images to analyze
      </label>
      <div class="flex flex-col gap-2 sm:flex-row">
        <Input
          id="vibecheck-pdf"
          name="pdf"
          type="file"
          accept=".pdf,application/pdf,image/jpeg,image/png,image/tiff,image/bmp"
          multiple
          data-testid="vibecheck-pdf-input"
          onChange={(event) => {
            const next = Array.from(event.currentTarget.files ?? []);
            setSelectedFiles(next);
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
      <Show when={selectionCopy()}>
        {(copy) => (
          <p class="text-xs text-muted-foreground" data-testid="upload-selection-copy">
            {copy()}
          </p>
        )}
      </Show>
      <p class="text-xs text-muted-foreground" data-testid="pdf-upload-copy">
        PDF up to {MAX_PDF_LABEL}, or up to {MAX_IMAGE_COUNT} images /{" "}
        {MAX_IMAGE_BATCH_LABEL} total.
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
