import { Show, type JSX } from "solid-js";
import { A } from "@solidjs/router";
import { Button } from "@opennotes/ui/components/ui/button";
import type { ErrorCode } from "~/lib/api-client.server";
import { analyzeAction } from "~/routes/analyze.data";

export interface JobFailureCardProps {
  url: string;
  errorCode: ErrorCode | null;
  errorMessage?: string | null;
  errorHost?: string | null;
  onTryAgain?: () => void;
}

function copyFor(
  code: ErrorCode | null,
  errorHost: string | null | undefined,
): string {
  switch (code) {
    case "invalid_url":
      return "That URL couldn't be parsed.";
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

export default function JobFailureCard(props: JobFailureCardProps): JSX.Element {
  const copy = () => copyFor(props.errorCode, props.errorHost);

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

      <Show when={props.errorMessage}>
        {(msg) => (
          <p class="text-xs text-muted-foreground" data-testid="job-failure-detail">
            {msg()}
          </p>
        )}
      </Show>

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
