import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";

type FactsClaims = components["schemas"]["FactsClaimsSection"];
type DedupedClaim = components["schemas"]["DedupedClaim"];
type FactCheckMatch = components["schemas"]["FactCheckMatch"];

export interface FactsClaimsSectionProps {
  factsClaims: FactsClaims;
}

function DedupedClaimsList(props: { claims: DedupedClaim[] }) {
  const sorted = createMemo(() =>
    [...props.claims].sort(
      (a, b) => (b.occurrence_count ?? 0) - (a.occurrence_count ?? 0),
    ),
  );

  return (
    <div
      data-testid="deduped-claims-entry"
      class="space-y-2 border-l-2 border-chart-1 pl-3"
    >
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Deduped claims ({sorted().length})
      </p>
      <Show
        when={sorted().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No repeated claims identified.
          </p>
        }
      >
        <ul data-testid="deduped-claims-list" class="space-y-1.5">
          <For each={sorted()}>
            {(claim) => (
              <li data-testid="deduped-claim-item" class="text-xs">
                <p class="text-foreground">{claim.canonical_text}</p>
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
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

function KnownMisinfoList(props: { items: FactCheckMatch[] }) {
  // Group by claim_text so each claim has its review(s) nested under it.
  const grouped = createMemo(() => {
    const map = new Map<string, FactCheckMatch[]>();
    for (const item of props.items) {
      const list = map.get(item.claim_text);
      if (list) list.push(item);
      else map.set(item.claim_text, [item]);
    }
    return Array.from(map.entries());
  });

  return (
    <div
      data-testid="known-misinfo-entry"
      class="space-y-2 border-l-2 border-destructive pl-3"
    >
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Known misinformation ({grouped().length})
      </p>
      <Show
        when={grouped().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No known-misinformation matches.
          </p>
        }
      >
        <ul class="space-y-2">
          <For each={grouped()}>
            {([claimText, reviews]) => (
              <li
                data-testid="known-misinfo-item"
                class="rounded-md border border-border bg-background p-2 text-xs"
              >
                <p class="text-foreground">{claimText}</p>
                <ul class="mt-1.5 space-y-1">
                  <For each={reviews}>
                    {(review) => (
                      <li class="flex items-center justify-between gap-2">
                        <div class="min-w-0 flex-1">
                          <span class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
                            {review.textual_rating}
                          </span>
                          <span class="ml-2 truncate text-[11px] text-muted-foreground">
                            {review.publisher}
                          </span>
                        </div>
                        <a
                          href={review.review_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          class="shrink-0 text-[11px] text-primary underline-offset-2 hover:underline"
                        >
                          fact check
                        </a>
                      </li>
                    )}
                  </For>
                </ul>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

export default function FactsClaimsSection(props: FactsClaimsSectionProps) {
  return (
    <section
      aria-labelledby="sidebar-facts-heading"
      data-testid="sidebar-facts-claims"
      class="space-y-3 rounded-lg border border-border bg-card p-4"
    >
      <header>
        <h3
          id="sidebar-facts-heading"
          class="flex items-center gap-2 text-sm font-semibold text-foreground"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect x="3" y="2" width="10" height="12" rx="1" />
            <path d="M6 5h4M6 8h4M6 11h2" />
          </svg>
          Facts &amp; claims
        </h3>
      </header>

      <div class="space-y-3">
        <DedupedClaimsList
          claims={props.factsClaims.claims_report.deduped_claims}
        />
        <KnownMisinfoList
          items={props.factsClaims.known_misinformation ?? []}
        />
      </div>
    </section>
  );
}
