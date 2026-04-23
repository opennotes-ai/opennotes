import { For, Match, Show, Switch, createMemo, type JSX } from "solid-js";
import type { SectionSlot, SectionSlug } from "~/lib/api-client.server";
import { SKELETONS } from "./skeletons";
import RetryButton from "./RetryButton";

export type SlugToSlots = Partial<Record<SectionSlug, SectionSlot>>;

export interface SectionGroupProps {
  label: string;
  slugs: SectionSlug[];
  sections: SlugToSlots;
  render: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>>;
  jobId?: string;
  onRetry?: (slug: SectionSlug) => void;
}

function slotFor(sections: SlugToSlots, slug: SectionSlug): SectionSlot {
  const existing = sections[slug];
  if (existing) return existing;
  return { state: "pending", attempt_id: "" };
}

function slugHeadingLabel(slug: SectionSlug): string {
  switch (slug) {
    case "safety__moderation":
      return "Moderation";
    case "tone_dynamics__flashpoint":
      return "Flashpoint";
    case "tone_dynamics__scd":
      return "Speaker dynamics";
    case "facts_claims__dedup":
      return "Deduped claims";
    case "facts_claims__known_misinfo":
      return "Known misinformation";
    case "opinions_sentiments__sentiment":
      return "Sentiment";
    case "opinions_sentiments__subjective":
      return "Subjective claims";
  }
}

export default function SectionGroup(props: SectionGroupProps): JSX.Element {
  const doneCount = createMemo(() =>
    props.slugs.reduce(
      (acc, slug) => acc + (slotFor(props.sections, slug).state === "done" ? 1 : 0),
      0,
    ),
  );
  const totalCount = () => props.slugs.length;

  return (
    <section
      data-testid={`section-group-${props.label}`}
      class="flex flex-col gap-4 rounded-lg bg-card p-4 text-card-foreground shadow-sm"
    >
      <header class="flex items-baseline justify-between gap-2">
        <h3 class="text-sm font-semibold text-foreground">{props.label}</h3>
        <span
          data-testid="section-group-counter"
          class="font-mono text-[11px] tabular-nums text-muted-foreground"
        >
          {props.label} &middot; {doneCount()}/{totalCount()}
        </span>
      </header>

      <div class="flex flex-col gap-4">
        <For each={props.slugs}>
          {(slug) => {
            const slot = () => slotFor(props.sections, slug);
            const Skeleton = SKELETONS[slug];
            const heading = slugHeadingLabel(slug);
            return (
              <div
                data-testid={`slot-${slug}`}
                data-slot-state={slot().state}
                class="flex flex-col gap-2"
              >
                <p
                  data-testid={`slot-label-${slug}`}
                  data-dimmed={slot().state === "pending" ? "true" : "false"}
                  class={
                    slot().state === "pending"
                      ? "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground opacity-60"
                      : "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                  }
                >
                  {heading}
                </p>
                <Switch>
                  <Match when={slot().state === "pending"}>
                    {/* pending: label only, no body */}
                    <span class="sr-only">pending</span>
                  </Match>
                  <Match when={slot().state === "running"}>
                    <Skeleton />
                  </Match>
                  <Match when={slot().state === "done"}>
                    <Show when={props.render[slug]}>
                      {(renderFn) => (
                        <div
                          class="section-reveal"
                          data-slot-attempt-id={slot().attempt_id}
                        >
                          {renderFn()(slot().data)}
                        </div>
                      )}
                    </Show>
                  </Match>
                  <Match when={slot().state === "failed"}>
                    <div class="flex flex-col gap-1 text-xs text-muted-foreground">
                      <p>Couldn't run this analysis.</p>
                      <Show
                        when={props.jobId}
                        fallback={
                          <button
                            type="button"
                            data-testid={`retry-${slug}`}
                            onClick={() => props.onRetry?.(slug)}
                            class="self-start text-[11px] font-medium text-primary underline-offset-2 hover:underline"
                          >
                            Retry
                          </button>
                        }
                      >
                        {(jobId) => (
                          <RetryButton
                            jobId={jobId()}
                            slug={slug}
                            slotState={slot().state}
                            onSuccess={() => props.onRetry?.(slug)}
                          />
                        )}
                      </Show>
                    </div>
                  </Match>
                </Switch>
              </div>
            );
          }}
        </For>
      </div>
    </section>
  );
}
