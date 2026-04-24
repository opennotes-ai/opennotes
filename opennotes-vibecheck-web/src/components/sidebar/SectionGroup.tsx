import {
  For,
  Match,
  Show,
  Switch,
  createEffect,
  createMemo,
  createSignal,
  untrack,
  type JSX,
} from "solid-js";
import type { SectionSlot } from "~/lib/api-client.server";
import type {
  PartialSectionSlots,
  SectionSlugLiteral,
} from "~/lib/section-slots";
import { SKELETONS } from "./skeletons";
import RetryButton from "./RetryButton";
import { sectionDisplayName } from "./display";

export type SlugToSlots = PartialSectionSlots;

export interface SectionGroupProps {
  label: string;
  slugs: SectionSlugLiteral[];
  sections: SlugToSlots;
  render: Partial<Record<SectionSlugLiteral, (data: unknown) => JSX.Element>>;
  emptinessChecks?: Partial<
    Record<SectionSlugLiteral, (data: unknown) => boolean>
  >;
  jobId?: string;
  onRetry?: (slug: SectionSlugLiteral) => void;
  cachedHint?: boolean;
}

function slotFor(
  sections: SlugToSlots,
  slug: SectionSlugLiteral,
): SectionSlot {
  const existing = sections[slug];
  if (existing) return existing;
  return { state: "pending", attempt_id: "" };
}

function slugHeadingLabel(slug: SectionSlugLiteral): string {
  switch (slug) {
    case "safety__moderation":
      return "Moderation";
    case "safety__web_risk":
      return "Web Risk";
    case "safety__image_moderation":
      return "Images";
    case "safety__video_moderation":
      return "Videos";
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

function defaultOpenFor(
  slot: SectionSlot,
  emptinessCheck: ((data: unknown) => boolean) | undefined,
): boolean {
  switch (slot.state) {
    case "pending":
      return false;
    case "running":
    case "failed":
      return true;
    case "done":
      return emptinessCheck ? !emptinessCheck(slot.data) : true;
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

  const announced = new Set<string>();
  const [announcement, setAnnouncement] = createSignal("");

  createEffect(() => {
    for (const slug of props.slugs) {
      const slot = slotFor(props.sections, slug);
      if (slot.state !== "done" && slot.state !== "failed") continue;
      const attemptId = slot.attempt_id ?? "";
      if (!attemptId) continue;
      const key = `${slug}:${slot.state}:${attemptId}`;
      if (announced.has(key)) continue;
      announced.add(key);
      const display = sectionDisplayName(slug);
      const verb = slot.state === "done" ? "complete" : "failed";
      setAnnouncement(`${display} ${verb}`);
    }
  });

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

      <span
        data-testid={`section-group-announce-${props.label}`}
        aria-live="polite"
        role="status"
        class="sr-only"
      >
        {announcement()}
      </span>

      <div class="flex flex-col gap-4">
        <For each={props.slugs}>
          {(slug) => {
            const slot = () => slotFor(props.sections, slug);
            const Skeleton = SKELETONS[slug];
            const heading = slugHeadingLabel(slug);
            const bodyId = `slot-body-${slug}`;
            const [userOpen, setUserOpen] = createSignal<boolean | null>(null);
            const isOpen = createMemo(
              () =>
                userOpen() ??
                defaultOpenFor(slot(), props.emptinessChecks?.[slug]),
            );
            const toggle = () => setUserOpen((current) => !(current ?? isOpen()));
            return (
              <div
                data-testid={`slot-${slug}`}
                data-slot-state={slot().state}
                data-cached-hint={props.cachedHint ? "1" : undefined}
                class="flex flex-col gap-2"
              >
                <button
                  type="button"
                  data-testid={`slot-toggle-${slug}`}
                  data-dimmed={slot().state === "pending" ? "true" : "false"}
                  aria-expanded={isOpen() ? "true" : "false"}
                  aria-controls={bodyId}
                  onClick={toggle}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggle();
                    }
                  }}
                  class={
                    slot().state === "pending"
                      ? "flex items-center justify-between gap-2 rounded-sm text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground opacity-60 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      : "flex items-center justify-between gap-2 rounded-sm text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  }
                >
                  <span
                    data-testid={`slot-label-${slug}`}
                    data-dimmed={slot().state === "pending" ? "true" : "false"}
                  >
                    {heading}
                  </span>
                  <span aria-hidden="true">{isOpen() ? "-" : "+"}</span>
                </button>
                <Show when={isOpen()}>
                  <div id={bodyId}>
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
                          {(renderFn) => {
                            // Polling fires `slot()` on every tick (~1.5s) with
                            // freshly-parsed data objects. Without this memo the
                            // inline `renderFn()(slot().data)` below re-evaluates
                            // every tick, producing a brand-new JSX tree and
                            // unmounting+remounting the report's DOM — which
                            // flickered <img>/<iframe> children as they reloaded.
                            // Mirrors the PR #409 fix for PageFrame.
                            const attemptKey = createMemo(() => {
                              const s = slot();
                              return s.state === "done" && s.attempt_id
                                ? s.attempt_id
                                : null;
                            });
                            const rendered = createMemo(() => {
                              const key = attemptKey();
                              if (!key) return null;
                              return untrack(() => renderFn()(slot().data));
                            });
                            return (
                              <div
                                class="section-reveal"
                                data-slot-attempt-id={slot().attempt_id}
                              >
                                {rendered()}
                              </div>
                            );
                          }}
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
                </Show>
              </div>
            );
          }}
        </For>
      </div>
    </section>
  );
}
