import { For, Show } from "solid-js";
import { Card } from "@opennotes/ui/components/ui/card";
import type { components } from "~/lib/generated-types";

type ToneDynamics = components["schemas"]["ToneDynamicsSection"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type SCDReport = components["schemas"]["SCDReport"];

export interface ToneDynamicsSectionProps {
  toneDynamics: ToneDynamics;
}

function FlashpointEntry(props: { matches: FlashpointMatch[] }) {
  return (
    <div
      data-testid="flashpoint-entry"
      class="space-y-2 border-l-2 border-chart-3 pl-3"
    >
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Flashpoint ({props.matches.length})
      </p>
      <Show
        when={props.matches.length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No flashpoint moments detected.
          </p>
        }
      >
        <ul class="space-y-1.5">
          <For each={props.matches}>
            {(match) => (
              <li class="text-xs">
                <div class="flex items-center gap-2">
                  <span
                    data-testid="flashpoint-risk-level"
                    class="inline-flex items-center rounded-full bg-chart-3/15 px-1.5 py-0.5 text-[10px] font-medium text-foreground"
                  >
                    {match.risk_level}
                  </span>
                  <span class="font-mono text-[10px] text-muted-foreground">
                    {match.derailment_score}/100
                  </span>
                </div>
                <p class="mt-1 line-clamp-2 text-foreground">
                  {match.reasoning}
                </p>
                <p class="mt-0.5 font-mono text-[10px] text-muted-foreground">
                  utterance {match.utterance_id}
                </p>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

function SCDEntry(props: { scd: SCDReport }) {
  const toneLabels = (): string[] => props.scd.tone_labels ?? [];
  const speakerEntries = (): [string, string][] =>
    Object.entries(props.scd.per_speaker_notes ?? {});

  return (
    <div
      data-testid="scd-entry"
      class="space-y-2 border-l-2 border-chart-2 pl-3"
    >
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        SCD
      </p>
      <Show when={props.scd.insufficient_conversation}>
        <p
          data-testid="scd-insufficient"
          class="rounded-md bg-muted px-2 py-1 text-[11px] italic text-muted-foreground"
        >
          Input lacked a multi-speaker exchange.
        </p>
      </Show>
      <Show when={props.scd.summary}>
        <p class="text-xs text-foreground">{props.scd.summary}</p>
      </Show>
      <Show when={toneLabels().length > 0}>
        <div class="flex flex-wrap gap-1">
          <For each={toneLabels()}>
            {(label) => (
              <span
                data-testid="scd-tone-label"
                class="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
              >
                {label}
              </span>
            )}
          </For>
        </div>
      </Show>
      <Show when={speakerEntries().length > 0}>
        <ul class="space-y-1">
          <For each={speakerEntries()}>
            {([speaker, note]) => (
              <li class="text-[11px]">
                <span class="font-semibold text-foreground">{speaker}:</span>{" "}
                <span class="text-muted-foreground">{note}</span>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

export default function ToneDynamicsSection(
  props: ToneDynamicsSectionProps,
) {
  return (
    <Card
      role="region"
      aria-labelledby="sidebar-tone-heading"
      data-testid="sidebar-tone-dynamics"
      class="space-y-3 p-4"
    >
      <header>
        <h3
          id="sidebar-tone-heading"
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
            <path d="M3 4h10v7H6l-3 3V4z" />
          </svg>
          Tone &amp; dynamics
        </h3>
      </header>

      <div class="space-y-3">
        <FlashpointEntry
          matches={props.toneDynamics.flashpoint_matches ?? []}
        />
        <SCDEntry scd={props.toneDynamics.scd} />
      </div>
    </Card>
  );
}
