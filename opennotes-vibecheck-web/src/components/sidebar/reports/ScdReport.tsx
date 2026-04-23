import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";

type SCDReport = components["schemas"]["SCDReport"];
type SpeakerArc = components["schemas"]["SpeakerArc"];

const INSUFFICIENT_COPY =
  "Not enough back-and-forth to read the room here.";

function formatRange(range: number[] | null | undefined): string | null {
  if (!range || range.length !== 2) return null;
  const [start, end] = range;
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return `turns ${start}-${end}`;
}

export interface ScdReportProps {
  scd: SCDReport;
}

export default function ScdReport(props: ScdReportProps): JSX.Element {
  const narrativeText = (): string => {
    const narrative = (props.scd.narrative ?? "").trim();
    if (narrative.length > 0) return narrative;
    return (props.scd.summary ?? "").trim();
  };
  const toneLabels = (): string[] => props.scd.tone_labels ?? [];
  const speakerArcs = (): SpeakerArc[] => props.scd.speaker_arcs ?? [];

  return (
    <div data-testid="report-tone_dynamics__scd" class="space-y-3">
      <Show
        when={!props.scd.insufficient_conversation}
        fallback={
          <p
            data-testid="scd-insufficient"
            class="text-xs italic text-muted-foreground"
          >
            {INSUFFICIENT_COPY}
          </p>
        }
      >
        <Show when={narrativeText().length > 0}>
          <p
            data-testid="scd-narrative"
            class="text-xs leading-relaxed text-foreground"
          >
            {narrativeText()}
          </p>
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

        <Show when={speakerArcs().length > 0}>
          <ul class="space-y-1.5">
            <For each={speakerArcs()}>
              {(arc) => {
                const rangeLabel = formatRange(arc.utterance_id_range);
                return (
                  <li
                    data-testid="scd-speaker-arc"
                    class="text-[11px] leading-snug"
                  >
                    <span class="font-semibold text-foreground">
                      {arc.speaker}
                    </span>
                    <span class="text-muted-foreground"> &mdash; {arc.note}</span>
                    <Show when={rangeLabel}>
                      {(label) => (
                        <span
                          data-testid="scd-arc-range"
                          aria-label={label()}
                          class="ml-1 inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                        >
                          {label()}
                        </span>
                      )}
                    </Show>
                  </li>
                );
              }}
            </For>
          </ul>
        </Show>
      </Show>
    </div>
  );
}
