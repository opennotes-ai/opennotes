import { Show, type JSX } from "solid-js";
import { Button } from "@opennotes/ui/components/ui/button";
import { analyzeAction } from "~/routes/analyze.data";
import { FeedbackBell } from "./feedback/FeedbackBell";

export interface ExpiredAnalysisCardProps {
  url: string | null;
  expiredAt?: Date | null;
}

function tryExtractHost(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

export default function ExpiredAnalysisCard(props: ExpiredAnalysisCardProps): JSX.Element {
  const host = () => tryExtractHost(props.url);

  return (
    <section
      role="alert"
      data-testid="expired-analysis-card"
      class="relative flex w-full flex-col gap-4 rounded-lg border border-amber-400/40 bg-amber-50/5 p-6"
    >
      <header class="flex flex-col gap-1">
        <p
          class="text-sm font-semibold text-amber-600"
          data-testid="expired-analysis-title"
        >
          This analysis has expired
        </p>
        <Show when={props.expiredAt}>
          {(date) => (
            <p class="text-xs text-muted-foreground" data-testid="expired-analysis-date">
              Expired {date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
            </p>
          )}
        </Show>
        <Show when={props.url}>
          <p
            class="break-all text-xs text-muted-foreground"
            data-testid="expired-analysis-url"
          >
            {props.url}
          </p>
        </Show>
      </header>

      <p class="text-sm text-foreground" data-testid="expired-analysis-copy">
        This analysis is no longer available. Re-analyze to get a fresh result.
      </p>

      <div class="flex flex-wrap items-center gap-3">
        <Show
          when={props.url}
          fallback={
            <a
              href="/"
              data-testid="expired-analysis-home"
              class="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              Submit a new URL
            </a>
          }
        >
          <form
            action={analyzeAction}
            method="post"
            data-testid="expired-analysis-form"
            class="inline-flex"
          >
            <input type="hidden" name="url" value={props.url ?? ""} />
            <Button
              type="submit"
              size="sm"
              data-testid="expired-analysis-reanalyze"
              aria-label={`Re-analyze ${host() ?? props.url}`}
            >
              Re-analyze
            </Button>
          </form>
        </Show>
      </div>
      <FeedbackBell bell_location="card:expired-analysis" />
    </section>
  );
}
