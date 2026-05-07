import { Show, createSignal, type JSX } from "solid-js";
import { useAction } from "@solidjs/router";
import { Link } from "@opennotes/ui/components/ui/link";
import type { SectionSlug } from "~/lib/api-client.server";
import { retrySectionAction } from "~/routes/analyze.data";
import { sectionDisplayName } from "./display";

export interface RetryButtonProps {
  jobId: string;
  slug: SectionSlug;
  slotState: "pending" | "running" | "done" | "failed";
  onSuccess?: () => void;
}

export default function RetryButton(props: RetryButtonProps): JSX.Element {
  const submitRetry = useAction(retrySectionAction);
  const [inFlight, setInFlight] = createSignal(false);
  const [inlineError, setInlineError] = createSignal<string | null>(null);

  const baseDisabled = () => props.slotState !== "failed";
  const disabled = () => baseDisabled() || inFlight();

  const handleClick = async () => {
    if (disabled()) return;
    setInlineError(null);
    setInFlight(true);
    const fd = new FormData();
    fd.set("job_id", props.jobId);
    fd.set("slug", props.slug);
    try {
      await submitRetry(fd);
      props.onSuccess?.();
    } catch (err: unknown) {
      console.error(
        `RetryButton: retry for ${props.slug} failed`,
        err,
      );
      setInlineError("Retry failed. Try again.");
    } finally {
      setInFlight(false);
    }
  };

  return (
    <div class="flex flex-col gap-1">
      <Link
        size="sm"
        variant="default"
        data-testid={`retry-${props.slug}`}
        data-in-flight={inFlight() ? "true" : "false"}
        aria-label={`Retry ${sectionDisplayName(props.slug)}`}
        disabled={disabled()}
        onClick={handleClick}
        class="self-start"
      >
        {inFlight() ? "Retrying..." : "Retry"}
      </Link>
      <Show when={inlineError()}>
        {(msg) => (
          <p
            data-testid={`retry-error-${props.slug}`}
            class="text-[11px] text-destructive"
          >
            {msg()}
          </p>
        )}
      </Show>
    </div>
  );
}
