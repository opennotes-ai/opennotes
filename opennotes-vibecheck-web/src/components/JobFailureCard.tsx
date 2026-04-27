import { For, Show, type JSX } from "solid-js";
import { A } from "@solidjs/router";
import { Button } from "@opennotes/ui/components/ui/button";
import type { ErrorCode } from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";
import { analyzeAction } from "~/routes/analyze.data";

type WebRiskFinding = components["schemas"]["WebRiskFinding"];

export interface JobFailureCardProps {
  url: string;
  errorCode: ErrorCode | null;
  errorHost?: string | null;
  webRiskFindings?: WebRiskFinding[];
  onTryAgain?: () => void;
}

function copyFor(
  code: ErrorCode | null,
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
      return "We couldn't extract content from that page.";
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
// `ErrorCode`. Backend `error_message` stays populated for ops/log
// correlation but is no longer threaded into this component.
function detailFor(code: ErrorCode | null): string {
  switch (code) {
    case "invalid_url":
      return "Check the URL is correctly formed and try again.";
    case "unsafe_url":
      return "Web Risk flagged this URL as unsafe.";
    case "unsupported_site":
      return "This site blocks automated readers.";
    case "upstream_error":
      return "Try again in a moment — the page wasn't reachable.";
    case "extraction_failed":
      return "We couldn't pull readable content from that page.";
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

      <div class="flex flex-wrap items-center gap-3">
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
        <A
          href="/"
          data-testid="job-failure-home"
          class="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Back to home
        </A>
      </div>
    </section>
  );
}
