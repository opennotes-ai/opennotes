import { For, Show, type JSX } from "solid-js";
import { Button } from "@opennotes/ui/components/ui/button";
import type { PublicErrorCode } from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";
import { analyzeAction } from "~/routes/analyze.data";

type WebRiskFinding = components["schemas"]["WebRiskFinding"];

function isHttpUrl(candidate: string): boolean {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export interface JobFailureCardProps {
  url: string;
  errorCode: PublicErrorCode | null;
  errorHost?: string | null;
  webRiskFindings?: WebRiskFinding[];
  onTryAgain?: () => void;
}

function copyFor(
  code: PublicErrorCode | null,
  errorHost: string | null | undefined,
): string {
  switch (code) {
    case "invalid_url":
      return "That URL couldn't be parsed.";
    case "unsafe_url":
      return "Web Risk flagged this URL before analysis.";
    case "unsupported_site":
      return `We can't analyze ${errorHost ?? "that site"} yet.`;
    case "upstream_error":
      return "The analyzer couldn't reach that page.";
    case "extraction_failed":
      return "We couldn't read this page's content.";
    case "pdf_too_large":
      return "This PDF is too large to analyze.";
    case "pdf_extraction_failed":
      return "We couldn't extract text from this PDF.";
    case "upload_key_invalid":
    case "upload_not_found":
      return "The PDF upload could not be found.";
    case "invalid_pdf_type":
      return "That file type isn't supported — please upload a PDF.";
    case "section_failure":
      return "Some analysis sections couldn't be completed.";
    case "timeout":
      return "The analysis took too long and was cancelled.";
    case "rate_limited":
      return "Too many recent requests. Try again in a moment.";
    case "internal":
    case null:
    default:
      return "Something went wrong. Please try again.";
  }
}

// TASK-1488.19: curated per-code detail strings rendered as the second
// line below `copyFor()`. Replaces the previous behavior of rendering
// the BE's `error_message` prose, which leaked vendor implementation
// details (e.g. raw Firecrawl 403 envelopes) into customer-facing UI.
// Decision recorded in the task: friendly-replace at the FE for every
// `PublicErrorCode`. Backend `error_message` stays populated for ops/log
// correlation but is no longer threaded into this component.
function detailFor(code: PublicErrorCode | null): string {
  switch (code) {
    case "invalid_url":
      return "Check the URL is correctly formed and try again.";
    case "unsafe_url":
      return "Web Risk flagged this URL as unsafe.";
    case "unsupported_site":
      return "This site blocks automated readers.";
    case "upstream_error":
      return "The site may be blocking automated readers, or it could be a temporary outage — try again in a moment.";
    case "extraction_failed":
      return "This often happens when a site blocks automated readers (login walls, paywalls, captchas, or bot protection).";
    case "pdf_too_large":
      return "Please upload a PDF that is 50 MB or smaller.";
    case "pdf_extraction_failed":
      return "Your PDF may be encrypted or image-only. Try a different file.";
    case "upload_key_invalid":
    case "upload_not_found":
      return "The upload session expired or was not found. Please try uploading again.";
    case "invalid_pdf_type":
      return "Only PDF files are supported. Please select a valid PDF and try again.";
    case "section_failure":
      return "Some analysis sections couldn't complete.";
    case "timeout":
      return "Try again in a moment — the analysis didn't finish in time.";
    case "rate_limited":
      return "Too many recent requests. Try again shortly.";
    case "internal":
    case null:
    default:
      return "Something went wrong. Please try again or contact support.";
  }
}

function showsPdfSuggestion(code: PublicErrorCode | null): boolean {
  return (
    code === "upstream_error" ||
    code === "extraction_failed" ||
    code === "unsupported_site" ||
    code === "timeout"
  );
}

function threatLabel(threat: WebRiskFinding["threat_types"][number]): string {
  return threat.replaceAll("_", " ").toLowerCase();
}

export default function JobFailureCard(props: JobFailureCardProps): JSX.Element {
  const copy = () => copyFor(props.errorCode, props.errorHost);
  const detail = () => detailFor(props.errorCode);
  const webRiskFindings = (): WebRiskFinding[] => props.webRiskFindings ?? [];

  return (
    <section
      role="alert"
      data-testid="job-failure-card"
      data-error-code={props.errorCode ?? "internal"}
      class="flex w-full flex-col gap-4 rounded-lg border border-destructive/40 bg-destructive/5 p-6"
    >
      <header class="flex flex-col gap-1">
        <p class="text-sm font-semibold text-destructive">
          Analysis failed
        </p>
        <p class="break-all text-xs text-muted-foreground" data-testid="job-failure-url">
          {props.url}
        </p>
      </header>

      <p class="text-sm text-foreground" data-testid="job-failure-copy">
        {copy()}
      </p>

      <Show when={props.errorCode === "unsafe_url" && webRiskFindings().length > 0}>
        <ul class="space-y-2">
          <For each={webRiskFindings()}>
            {(finding) => (
              <li
                data-testid="unsafe-url-finding"
                class="rounded-md border border-destructive/30 bg-background p-3 text-xs"
              >
                <p class="break-all font-medium text-foreground">
                  {finding.url}
                </p>
                <div class="mt-2 flex flex-wrap gap-1">
                  <For each={finding.threat_types}>
                    {(threat) => (
                      <span
                        data-testid="unsafe-url-threat"
                        class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                      >
                        {threatLabel(threat)}
                      </span>
                    )}
                  </For>
                </div>
              </li>
            )}
          </For>
        </ul>
      </Show>

      <p class="text-xs text-muted-foreground" data-testid="job-failure-detail">
        {detail()}
      </p>

      <Show when={showsPdfSuggestion(props.errorCode)}>
        <p class="text-xs text-muted-foreground" data-testid="job-failure-pdf-suggestion">
          Can't access this page?{" "}
          <a href="/#pdf-upload" class="underline underline-offset-4 hover:text-foreground">
            Print it as a PDF and upload it for analysis.
          </a>
        </p>
      </Show>

      <div class="flex flex-wrap items-center gap-3">
        <Show when={isHttpUrl(props.url)}>
          <form
            action={analyzeAction}
            method="post"
            data-testid="job-failure-try-again-form"
            onSubmit={() => props.onTryAgain?.()}
            class="inline-flex"
          >
            <input type="hidden" name="url" value={props.url} />
            <Button type="submit" size="sm" data-testid="job-failure-try-again">
              Try again
            </Button>
          </form>
        </Show>
        <a
          href="/"
          data-testid="job-failure-home"
          class="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Back to home
        </a>
      </div>
    </section>
  );
}
