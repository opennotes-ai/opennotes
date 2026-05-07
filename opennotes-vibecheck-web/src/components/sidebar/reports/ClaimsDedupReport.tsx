import {
  For,
  Show,
  createEffect,
  createMemo,
  createSignal,
  createUniqueId,
  onCleanup,
} from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import UtteranceRef from "../UtteranceRef";

type ClaimsReport = components["schemas"]["ClaimsReport"];
type DedupedClaim = components["schemas"]["DedupedClaim"];
type ClaimCategory = components["schemas"]["ClaimCategory"];
type Premise = components["schemas"]["Premise"];
type SupportingFact = components["schemas"]["SupportingFact"];

const CATEGORY_ORDER: ClaimCategory[] = [
  "potentially_factual",
  "predictions",
  "self_claims",
  "subjective",
  "other",
];

const CATEGORY_LABELS: Record<ClaimCategory, string> = {
  potentially_factual: "Factual claims",
  predictions: "Predictions",
  self_claims: "Self-reported",
  subjective: "Value claims",
  other: "Other",
};

export interface ClaimsDedupReportProps {
  claimsReport: ClaimsReport;
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
  evidenceComplete?: boolean;
}

function sourceLabel(fact: SupportingFact): string {
  return fact.source_kind === "external" ? "external" : `turn ${fact.source_ref}`;
}

function safeExternalUrl(value: string): string | null {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

export default function ClaimsDedupReport(props: ClaimsDedupReportProps) {
  const claims = (): DedupedClaim[] =>
    props.claimsReport?.deduped_claims ?? [];

  const sorted = createMemo(() =>
    [...claims()].sort(
      (a, b) => (b.occurrence_count ?? 0) - (a.occurrence_count ?? 0),
    ),
  );
  const grouped = createMemo(() =>
    CATEGORY_ORDER.map((category) => ({
      category,
      claims: sorted().filter(
        (claim) => (claim.category ?? "potentially_factual") === category,
      ),
    })).filter((group) => group.claims.length > 0),
  );

  const [openPopoverId, setOpenPopoverId] = createSignal<string | null>(null);

  createEffect(() => {
    if (openPopoverId() === null) return;
    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node | null;
      const id = openPopoverId();
      if (!id || !target) return;
      const contentEl = document.getElementById(id);
      const triggerEl = document.querySelector(
        `[aria-controls="${id}"]`,
      );
      if (
        (triggerEl && triggerEl.contains(target)) ||
        (contentEl && contentEl.contains(target))
      ) {
        return;
      }
      setOpenPopoverId(null);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenPopoverId(null);
      }
    };
    document.addEventListener("click", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    onCleanup(() => {
      document.removeEventListener("click", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    });
  });

  return (
    <div data-testid="report-facts_claims__dedup" class="space-y-2">
      <p class="text-[11px] text-muted-foreground">
        {sorted().length} claim{sorted().length === 1 ? "" : "s"}
      </p>
      <Show
        when={sorted().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No repeated claims identified.
          </p>
        }
      >
        <div data-testid="deduped-claims-list" class="space-y-3">
          <For each={grouped()}>
            {(group) => (
              <section data-testid="deduped-claims-category" class="space-y-1.5">
                <h4 class="text-[11px] font-semibold text-muted-foreground">
                  {CATEGORY_LABELS[group.category]}
                </h4>
                <ul class="space-y-1.5">
                  <For each={group.claims}>
                    {(claim) => {
                      const popoverId = createUniqueId();
                      const isOpen = () => openPopoverId() === popoverId;
                      const utteranceIds = () => claim.utterance_ids ?? [];
                      const primaryId = () => utteranceIds()[0];
                      const remainingIds = () => utteranceIds().slice(1);
                      const supportingFacts = () =>
                        claim.supporting_facts ?? [];
                      const factsToVerify = () => claim.facts_to_verify ?? 0;
                      const isFactual = () =>
                        (claim.category ?? "potentially_factual") ===
                        "potentially_factual";
                      const premiseRegistry = () =>
                        props.claimsReport.premises?.premises ?? {};
                      const premises = (): Premise[] =>
                        (claim.premise_ids ?? [])
                          .map((id) => premiseRegistry()[id])
                          .filter((premise): premise is Premise => Boolean(premise));
                      const disabled = () =>
                        !props.canJumpToUtterance || !props.onUtteranceClick;
                      return (
                        <li data-testid="deduped-claim-item" class="text-xs">
                          <ExpandableText
                            text={claim.canonical_text}
                            lines={2}
                            testId="deduped-claim-text"
                            class="text-foreground"
                          />
                          <p class="mt-0.5 text-[11px] text-muted-foreground">
                            <span data-testid="deduped-claim-occurrences">
                              &times;{claim.occurrence_count}
                            </span>
                            <span class="mx-1">&middot;</span>
                            <span>
                              {claim.author_count} author
                              {claim.author_count === 1 ? "" : "s"}
                            </span>
                          </p>
                          <Show when={primaryId()}>
                            {(id) => (
                              <div
                                data-testid="deduped-claim-utterance-refs"
                                class="relative mt-1 flex flex-wrap items-center gap-1"
                              >
                                <UtteranceRef
                                  utteranceId={String(id())}
                                  label={`turn ${id()}`}
                                  onClick={props.onUtteranceClick ?? (() => undefined)}
                                  disabled={disabled()}
                                  testId="deduped-claim-utterance-ref"
                                />
                                <Show when={remainingIds().length > 0}>
                                  <button
                                    type="button"
                                    data-testid="deduped-claim-more-utterances"
                                    class="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                                    aria-expanded={isOpen() ? "true" : "false"}
                                    aria-haspopup="dialog"
                                    aria-controls={popoverId}
                                    onClick={() =>
                                      setOpenPopoverId((current) =>
                                        current === popoverId ? null : popoverId,
                                      )
                                    }
                                  >
                                    +{remainingIds().length} more
                                  </button>
                                  <Show when={isOpen()}>
                                    <div
                                      id={popoverId}
                                      role="dialog"
                                      aria-label={`${remainingIds().length} additional utterance reference${
                                        remainingIds().length === 1 ? "" : "s"
                                      }`}
                                      data-testid="deduped-claim-utterance-popover"
                                      class="absolute left-0 top-full z-10 mt-1 flex flex-wrap gap-1 rounded-md border border-border bg-popover p-2 shadow-md"
                                    >
                                      <For each={remainingIds()}>
                                        {(remainingId) => (
                                          <UtteranceRef
                                            utteranceId={String(remainingId)}
                                            label={`turn ${remainingId}`}
                                            onClick={props.onUtteranceClick ?? (() => undefined)}
                                            disabled={disabled()}
                                            testId="deduped-claim-popover-utterance-ref"
                                          />
                                        )}
                                      </For>
                                    </div>
                                  </Show>
                                </Show>
                              </div>
                            )}
                          </Show>
                          <Show when={supportingFacts().length > 0}>
                            <div
                              data-testid="deduped-claim-supporting-facts"
                              class="mt-2 space-y-1 rounded-md bg-muted/50 px-2 py-1.5"
                            >
                              <p class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                                Supporting facts
                              </p>
                              <ul class="space-y-1">
                                <For each={supportingFacts()}>
                                  {(fact) => {
                                    const externalUrl = () =>
                                      safeExternalUrl(fact.source_ref);
                                    return (
                                      <li
                                        data-testid="deduped-claim-supporting-fact"
                                        class="text-[11px] leading-5 text-foreground"
                                      >
                                        <span>{fact.statement}</span>
                                        <span class="ml-1 text-muted-foreground">
                                          ({sourceLabel(fact)})
                                        </span>
                                        <Show
                                          when={fact.source_kind === "utterance"}
                                          fallback={
                                            <Show when={externalUrl()}>
                                              {(href) => (
                                                <a
                                                  data-testid="deduped-claim-supporting-fact-link"
                                                  href={href()}
                                                  target="_blank"
                                                  rel="noreferrer"
                                                  class="ml-1 text-primary underline-offset-2 hover:underline"
                                                >
                                                  source
                                                </a>
                                              )}
                                            </Show>
                                          }
                                        >
                                          <UtteranceRef
                                            utteranceId={fact.source_ref}
                                            label={sourceLabel(fact)}
                                            onClick={props.onUtteranceClick ?? (() => undefined)}
                                            disabled={disabled()}
                                            testId="deduped-claim-supporting-fact-ref"
                                          />
                                        </Show>
                                      </li>
                                    );
                                  }}
                                </For>
                              </ul>
                            </div>
                          </Show>
                          <Show
                            when={
                              props.evidenceComplete !== false &&
                              isFactual() &&
                              supportingFacts().length === 0
                            }
                          >
                            <Show
                              when={factsToVerify() > 0}
                              fallback={
                                <p
                                  data-testid="deduped-claim-no-sources"
                                  class="mt-2 rounded-md bg-muted/50 px-2 py-1.5 text-[11px] text-muted-foreground"
                                >
                                  No sources extracted.
                                </p>
                              }
                            >
                              <p
                                data-testid="deduped-claim-facts-to-verify"
                                class="mt-2 inline-flex rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-muted-foreground"
                              >
                                {factsToVerify()} fact
                                {factsToVerify() === 1 ? "" : "s"} to verify
                              </p>
                            </Show>
                          </Show>
                          <Show when={premises().length > 0}>
                            <div
                              data-testid="deduped-claim-premises"
                              class="mt-2 space-y-1 rounded-md border-l-2 border-accent bg-accent/10 px-2 py-1.5"
                            >
                              <p class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                                This claim assumes
                              </p>
                              <ul class="space-y-1">
                                <For each={premises()}>
                                  {(premise) => (
                                    <li
                                      data-testid="deduped-claim-premise"
                                      class="text-[11px] leading-5 text-foreground"
                                    >
                                      {premise.statement}
                                    </li>
                                  )}
                                </For>
                              </ul>
                              <p
                                data-testid="deduped-claim-premise-followup"
                                class="text-[10px] text-muted-foreground"
                              >
                                {premises().length} assumption
                                {premises().length === 1 ? "" : "s"} to verify
                              </p>
                            </div>
                          </Show>
                        </li>
                      );
                    }}
                  </For>
                </ul>
              </section>
            )}
          </For>
        </div>
      </Show>
    </div>
  );
}
