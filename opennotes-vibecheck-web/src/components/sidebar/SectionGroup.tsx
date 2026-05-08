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
import { ChevronDown, CircleHelp } from "lucide-solid";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@opennotes/ui/components/ui/popover";
import { Button } from "@opennotes/ui/components/ui/button";
import { Link } from "@opennotes/ui/components/ui/link";
import type { SectionSlot } from "~/lib/api-client.server";
import type {
  PartialSectionSlots,
  SectionSlugLiteral,
} from "~/lib/section-slots";
import { SKELETONS } from "./skeletons";
import RetryButton from "./RetryButton";
import { sectionDisplayName } from "./display";
import {
  sectionHelp,
  slotHelp,
  type SidebarHelpCopy,
} from "./help";

export type SlugToSlots = PartialSectionSlots;

export interface SectionGroupProps {
  label: string;
  slugs: SectionSlugLiteral[];
  sections: SlugToSlots;
  render: Partial<Record<SectionSlugLiteral, (data: unknown) => JSX.Element>>;
  defaultOpen?: boolean;
  summary?: {
    label?: string;
    content: () => JSX.Element;
    defaultOpen?: boolean;
  };
  emptinessChecks?: Partial<
    Record<SectionSlugLiteral, (data: unknown) => boolean>
  >;
  counts?: Partial<
    Record<SectionSlugLiteral, (data: unknown) => SlotCountBadge>
  >;
  jobId?: string;
  onRetry?: (slug: SectionSlugLiteral) => void;
  cachedHint?: boolean;
  renderRevision?: string | number | boolean;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function ChevronIcon(props: { expanded: boolean; testId: string }) {
  return (
    <ChevronDown
      data-testid={props.testId}
      data-icon="chevron-down"
      data-state={props.expanded ? "expanded" : "collapsed"}
      aria-hidden="true"
      size={12}
      strokeWidth={1.8}
      class={
        props.expanded
          ? "shrink-0 transition-transform duration-150"
          : "shrink-0 -rotate-90 transition-transform duration-150"
      }
    />
  );
}

export type SlotCountBadge = {
  total: number;
  flagged?: number;
  kind?: "results" | "flagged" | "sentences";
};

function asFiniteCount(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function formatCountBadge(count: SlotCountBadge): string {
  const total = asFiniteCount(count.total);
  if (count.kind === "flagged") {
    const flagged = asFiniteCount(count.flagged ?? 0);
    return `${flagged} (of ${total}) flagged`;
  }
  if (count.kind === "sentences") {
    if (total <= 0) return "no sentences scored";
    if (total === 1) return "based on 1 sentence";
    return `based on ${total} sentences`;
  }
  if (total <= 0) return "no results";
  if (total === 1) return "1 result";
  return `${total} results`;
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
    case "facts_claims__evidence":
      return "Claim evidence";
    case "facts_claims__premises":
      return "Claim premises";
    case "facts_claims__known_misinfo":
      return "Known misinformation";
    case "opinions_sentiments__sentiment":
      return "Sentiment";
    case "opinions_sentiments__subjective":
      return "Subjective claims";
    case "opinions_sentiments__trends_oppositions":
      return "Trends/oppositions";
    case "opinions_sentiments__highlights":
      return "Highlights";
  }
}

function HelpPopover(props: {
  copy: SidebarHelpCopy | null;
  triggerTestId: string;
  contentTestId: string;
  label: string;
}) {
  return (
    <Show when={props.copy}>
      {(copy) => (
        <Popover>
          <PopoverTrigger
            as={Button}
            size="icon-sm"
            variant="ghost"
            type="button"
            data-testid={props.triggerTestId}
            aria-label={`What does ${props.label} mean?`}
            class="size-6 shrink-0 text-muted-foreground"
          >
            <CircleHelp
              aria-hidden="true"
              data-icon="circle-help"
              size={14}
              strokeWidth={1.9}
            />
          </PopoverTrigger>
          <PopoverContent
            data-testid={props.contentTestId}
            class="max-w-xs space-y-2 text-xs leading-relaxed"
          >
            <p>
              <span class="font-semibold text-foreground">
                What we look for:
              </span>{" "}
              {copy().looksFor}
            </p>
            <p>
              <span class="font-semibold text-foreground">
                What these results mean:
              </span>{" "}
              {copy().means}
            </p>
          </PopoverContent>
        </Popover>
      )}
    </Show>
  );
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
  const lastSlotStates = new Map<SectionSlugLiteral, SectionSlot["state"]>();
  const lastFinishedKeys = new Map<SectionSlugLiteral, string>();
  let announcedJobId = props.jobId ?? "";
  let initializedAnnouncements = false;
  const [announcement, setAnnouncement] = createSignal("");
  const [groupOpen, setGroupOpen] = createSignal(props.defaultOpen !== false);
  const [userToggledGroupOpen, setUserToggledGroupOpen] = createSignal(false);
  const labelSlug = slugify(props.label);
  const groupBodyId = `section-group-body-${labelSlug}`;
  const sectionToggleLabel = () =>
    `${groupOpen() ? "Collapse" : "Expand"} ${props.label} section`;

  const [summaryUserOpen, setSummaryUserOpen] = createSignal<boolean | null>(null);

  createEffect(() => {
    const jobId = props.jobId ?? "";
    if (jobId !== announcedJobId) {
      announced.clear();
      lastSlotStates.clear();
      lastFinishedKeys.clear();
      announcedJobId = jobId;
      initializedAnnouncements = false;
      setAnnouncement("");
      setUserToggledGroupOpen(false);
    }

    for (const slug of props.slugs) {
      const slot = slotFor(props.sections, slug);
      const previousState = lastSlotStates.get(slug);
      const previousKey = lastFinishedKeys.get(slug);
      lastSlotStates.set(slug, slot.state);

      if (slot.state !== "done" && slot.state !== "failed") {
        lastFinishedKeys.delete(slug);
        continue;
      }

      const attemptId = slot.attempt_id ?? "";
      if (!attemptId) {
        lastFinishedKeys.delete(slug);
        continue;
      }

      const key = `${jobId}:${slug}:${slot.state}:${attemptId}`;
      const wasFinished =
        previousState === "done" || previousState === "failed";
      const finishedKeyChanged =
        previousKey !== undefined && previousKey !== key;
      lastFinishedKeys.set(slug, key);

      if (
        !initializedAnnouncements ||
        announced.has(key) ||
        (wasFinished && !finishedKeyChanged)
      ) {
        continue;
      }

      announced.add(key);
      const display = sectionDisplayName(slug);
      const verb = slot.state === "done" ? "complete" : "failed";
      setAnnouncement(`${display} ${verb}`);
    }
    initializedAnnouncements = true;
  });

  createEffect(() => {
    if (userToggledGroupOpen()) return;
    setGroupOpen(props.defaultOpen !== false);
  });

  return (
    <section
      data-testid={`section-group-${props.label}`}
      class="flex flex-col gap-4 rounded-lg bg-card p-4 text-card-foreground shadow-sm"
    >
      <header class="flex items-start justify-between gap-2">
        <div class="flex min-w-0 items-center gap-1.5">
          <h3 class="flex min-w-0 items-center text-sm font-semibold text-foreground">
            <Button
              variant="ghost"
              type="button"
              data-testid={`section-toggle-${props.label}`}
              aria-label={sectionToggleLabel()}
              aria-expanded={groupOpen() ? "true" : "false"}
              aria-controls={groupBodyId}
              onClick={() => {
                setUserToggledGroupOpen(true);
                setGroupOpen((current) => !current);
              }}
              class="flex h-auto min-w-0 items-center gap-1.5 -mx-2 px-2 py-1 rounded-md text-sm font-semibold text-foreground hover:bg-muted/60 dark:hover:bg-muted/60 hover:text-foreground"
            >
              <ChevronIcon expanded={groupOpen()} testId="section-group-chevron" />
              {props.label}
            </Button>
          </h3>
          <HelpPopover
            copy={sectionHelp(props.label)}
            triggerTestId={`section-help-${props.label}`}
            contentTestId={`section-help-content-${props.label}`}
            label={props.label}
          />
        </div>
        <Show when={totalCount() > 0}>
          <span
            data-testid="section-group-counter"
            class="font-mono text-[11px] tabular-nums text-muted-foreground"
            aria-label={`${props.label}: ${doneCount()} of ${totalCount()} sections complete`}
          >
            {doneCount()}/{totalCount()}
          </span>
        </Show>
      </header>

      <span
        data-testid={`section-group-announce-${props.label}`}
        aria-live="polite"
        role="status"
        class="sr-only"
      >
        {announcement()}
      </span>

      <div
        data-testid={groupBodyId}
        id={groupBodyId}
        aria-hidden={groupOpen() ? "false" : "true"}
        hidden={!groupOpen()}
        class="flex flex-col gap-4"
      >
        <Show when={props.summary}>
          {(summary) => {
            const summaryId = `section-summary-body-${labelSlug}`;
            const isOpen = createMemo(
              () => summaryUserOpen() ?? (summary().defaultOpen ?? true),
            );
            const summaryToggleLabel = () =>
              `${isOpen() ? "Collapse" : "Expand"} ${summary().label ?? "Summary"} in ${props.label}`;
            const toggle = () => setSummaryUserOpen((current) => !(current ?? isOpen()));
            return (
              <div
                data-testid={`section-summary-${props.label}`}
                class="flex flex-col gap-2"
              >
                <div class="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    type="button"
                    data-testid={`section-summary-toggle-${props.label}`}
                    data-summary-label={summary().label ?? "Summary"}
                    aria-label={summaryToggleLabel()}
                    aria-expanded={isOpen() ? "true" : "false"}
                    aria-controls={summaryId}
                    onClick={toggle}
                    class="flex h-auto min-w-0 flex-1 items-center justify-between gap-2 -mx-2 px-2 py-1 rounded-md text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:bg-muted/60 dark:hover:bg-muted/60 hover:text-foreground"
                  >
                    <span>{summary().label ?? "Summary"}</span>
                    <span class="ml-auto flex items-center gap-2">
                      <ChevronIcon expanded={isOpen()} testId="section-summary-chevron" />
                    </span>
                  </Button>
                </div>
                <div
                  id={summaryId}
                  hidden={!isOpen()}
                  aria-hidden={isOpen() ? "false" : "true"}
                >
                  {summary().content()}
                </div>
              </div>
            );
          }}
        </Show>
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
            const countLabel = createMemo(() => {
              const current = slot();
              if (current.state !== "done") return null;
              return formatCountBadge(
                props.counts?.[slug]?.(current.data) ?? { flagged: 0, total: 0 },
              );
            });
            const toggle = () => setUserOpen((current) => !(current ?? isOpen()));
            return (
              <div
                data-testid={`slot-${slug}`}
                data-slot-state={slot().state}
                data-cached-hint={props.cachedHint ? "1" : undefined}
                class="flex flex-col gap-2"
              >
                <div class="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    type="button"
                    data-testid={`slot-toggle-${slug}`}
                    data-dimmed={slot().state === "pending" ? "true" : "false"}
                    aria-expanded={isOpen() ? "true" : "false"}
                    aria-controls={bodyId}
                    onClick={toggle}
                    class={
                      slot().state === "pending"
                        ? "flex h-auto min-w-0 flex-1 items-center justify-between gap-2 -mx-2 px-2 py-1 rounded-md text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground opacity-60 hover:bg-muted/60 dark:hover:bg-muted/60 hover:text-foreground"
                        : "flex h-auto min-w-0 flex-1 items-center justify-between gap-2 -mx-2 px-2 py-1 rounded-md text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:bg-muted/60 dark:hover:bg-muted/60 hover:text-foreground"
                    }
                  >
                    <span
                      data-testid={`slot-label-${slug}`}
                      data-dimmed={slot().state === "pending" ? "true" : "false"}
                    >
                      {heading}
                    </span>
                    <span class="ml-auto flex items-center gap-2">
                      <Show when={countLabel()}>
                        {(label) => (
                          <span
                            data-testid={`slot-count-${slug}`}
                            class="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium normal-case tracking-normal text-muted-foreground"
                          >
                            {label()}
                          </span>
                        )}
                      </Show>
                      <ChevronIcon expanded={isOpen()} testId="slot-chevron" />
                    </span>
                  </Button>
                  <HelpPopover
                    copy={slotHelp(slug)}
                    triggerTestId={`slot-help-${slug}`}
                    contentTestId={`slot-help-content-${slug}`}
                    label={heading}
                  />
                </div>
                <Show when={isOpen()}>
                  <div id={bodyId}>
                    <Switch>
                      <Match when={slot().state === "pending"}>
                        <span class="sr-only">pending</span>
                      </Match>
                      <Match when={slot().state === "running"}>
                        <Skeleton />
                      </Match>
                      <Match when={slot().state === "done"}>
                        <Show when={props.render[slug]}>
                          {(renderFn) => {
                            const attemptKey = createMemo(() => {
                              const s = slot();
                              return s.state === "done" && s.attempt_id
                                ? `${s.attempt_id}:${String(props.renderRevision ?? "")}`
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
                              <Link
                                size="sm"
                                variant="default"
                                data-testid={`retry-${slug}`}
                                onClick={() => props.onRetry?.(slug)}
                                class="self-start"
                              >
                                Retry
                              </Link>
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
