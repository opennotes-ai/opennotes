import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";

type SCDReport = components["schemas"]["SCDReport"];

export interface ScdReportProps {
  scd: SCDReport;
}

export default function ScdReport(props: ScdReportProps) {
  const toneLabels = (): string[] => props.scd.tone_labels ?? [];
  const speakerEntries = (): [string, string][] =>
    Object.entries(props.scd.per_speaker_notes ?? {});

  return (
    <div data-testid="report-tone_dynamics__scd" class="space-y-2">
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
