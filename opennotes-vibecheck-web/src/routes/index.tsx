import { Show, Suspense } from "solid-js";
import { useSearchParams, useSubmission, createAsync } from "@solidjs/router";
import { Title, Meta } from "@solidjs/meta";
import { siteUrl } from "~/lib/site-url";
import PdfUpload from "~/components/PdfUpload";
import UrlInput from "~/components/UrlInput";
import RecentlyVibeChecked, {
  RecentlyVibeCheckedSkeleton,
} from "~/components/RecentlyVibeChecked";
import { analyzeAction, submitPdfAnalysisAction } from "./analyze.data";
import { getRecentAnalyses } from "./index.data";

function errorLabelFor(
  code: string | undefined,
  host: string | undefined,
): string | null {
  if (!code) return null;
  switch (code) {
    case "invalid_url":
      return "That URL couldn't be parsed. Double-check the scheme and host.";
    case "unsupported_site":
      return host
        ? `We can't analyze ${host} yet. Try a different URL.`
        : "We can't analyze that site yet. Try a different URL.";
    case "pdf_too_large":
      return "PDF upload is limited to 50 MB.";
    case "pdf_extraction_failed":
      return "We couldn't extract text from this PDF. Try a different file.";
    case "upload_key_invalid":
    case "upload_not_found":
      return "Upload may not have completed. Please try uploading the PDF again.";
    case "invalid_pdf_type":
      return "Only PDF files are accepted.";
    case "upstream_error":
      return "The analyzer couldn't reach that page. Try again in a moment.";
    default:
      return "Something went wrong. Please try another URL.";
  }
}

export default function HomePage() {
  const [searchParams] = useSearchParams();
  const urlSubmission = useSubmission(analyzeAction);
  const pdfSubmission = useSubmission(submitPdfAnalysisAction);
  const recentAnalyses = createAsync(() => getRecentAnalyses());

  const errorMessage = () =>
    errorLabelFor(
      typeof searchParams.error === "string" ? searchParams.error : undefined,
      typeof searchParams.host === "string" ? searchParams.host : undefined,
    );

  return (
    <>
      <Title>vibecheck — URL and PDF analysis</Title>
      <Meta property="og:title" content="vibecheck — URL and PDF analysis" />
      <Meta property="og:description" content="Analyze URLs and PDFs for tone, claims, safety, and opinions." />
      <Meta property="og:url" content={siteUrl("/")} />
      <Meta property="og:image" content={siteUrl("/api/og")} />
      <Meta name="twitter:image" content={siteUrl("/api/og")} />
      <main class="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-10 px-4 py-16 text-center">
        <header class="space-y-4">
          <h1 class="text-5xl font-semibold tracking-tight sm:text-6xl">
            vibecheck
          </h1>
          <p class="mx-auto max-w-md text-lg text-muted-foreground">
            Analyze URLs and PDFs for tone, claims, safety, and opinions.
          </p>
        </header>

        <div class="flex w-full flex-col gap-6">
          <UrlInput
            action={analyzeAction}
            pending={urlSubmission.pending}
            autofocus
          />
          <div id="pdf-upload" class="flex w-full flex-col gap-2">
            <p class="text-sm text-muted-foreground">
              Have a PDF, or hit a paywall? Upload it here:
            </p>
            <PdfUpload pending={pdfSubmission.pending} />
          </div>
        </div>

        <Show when={errorMessage()}>
          {(message) => (
            <p role="alert" class="text-sm text-destructive">
              {message()}
            </p>
          )}
        </Show>

        <p class="text-xs text-muted-foreground">
          Results appear instantly for recently analyzed URLs. New URLs take a
          bit longer.
        </p>

        <Suspense fallback={<RecentlyVibeCheckedSkeleton />}>
          <RecentlyVibeChecked analyses={recentAnalyses() ?? []} />
        </Suspense>
      </main>
    </>
  );
}
