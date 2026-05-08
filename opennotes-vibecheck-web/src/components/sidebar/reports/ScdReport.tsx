import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import UtteranceRef from "../UtteranceRef";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type SCDReport = components["schemas"]["SCDReport"];
type SpeakerArc = components["schemas"]["SpeakerArc"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];
type UtteranceStreamType = components["schemas"]["UtteranceStreamType"];

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
  upstreamStreamType?: UtteranceStreamType | null;
  utterances?: UtteranceAnchor[];
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
}

export default function ScdReport(props: ScdReportProps): JSX.Element {
  const narrativeText = (): string => {
    const narrative = (props.scd.narrative ?? "").trim();
    if (narrative.length > 0) return narrative;
    return (props.scd.summary ?? "").trim();
  };
  const toneLabels = (): string[] => props.scd.tone_labels ?? [];
  const speakerArcs = (): SpeakerArc[] => props.scd.speaker_arcs ?? [];
  const showStreamDivergence = (): boolean => {
    const upstream =
      props.upstreamStreamType ?? props.scd.upstream_stream_type ?? "unknown";
    const observed = props.scd.observed_stream_type ?? "unknown";
    const rationale = (props.scd.disagreement_rationale ?? "").trim();
    return observed !== upstream && rationale.length > 0;
  };
  const utteranceIdForPosition = (position: number): string | null =>
    props.utterances?.find((anchor) => anchor.position === position)
      ?.utterance_id ?? null;

  return (
    <div data-testid="report-tone_dynamics__scd" class="relative space-y-3">
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
          <ExpandableText
            text={narrativeText()}
            lines={3}
            testId="scd-narrative"
            class="text-xs leading-relaxed text-foreground"
          />
        </Show>

        <Show when={showStreamDivergence()}>
          <p
            data-testid="scd-stream-divergence"
            class="rounded-md border border-border bg-muted/40 px-2 py-1.5 text-[11px] leading-snug text-muted-foreground"
          >
            This page was tagged as{" "}
            {props.upstreamStreamType ?? props.scd.upstream_stream_type ?? "unknown"},
            but the analyzer reads it as {props.scd.observed_stream_type}:{" "}
            {props.scd.disagreement_rationale}
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
                const startPosition = arc.utterance_id_range?.[0];
                const startUtteranceId =
                  typeof startPosition === "number"
                    ? utteranceIdForPosition(startPosition)
                    : null;
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
                        <UtteranceRef
                          utteranceId={startUtteranceId ?? ""}
                          label={label()}
                          onClick={props.onUtteranceClick ?? (() => undefined)}
                          disabled={
                            !startUtteranceId ||
                            !props.canJumpToUtterance ||
                            !props.onUtteranceClick
                          }
                          testId="scd-arc-range"
                          ariaLabel={label()}
                          class="ml-1"
                        />
                      )}
                    </Show>
                  </li>
                );
              }}
            </For>
          </ul>
        </Show>
      </Show>
      <FeedbackBell bell_location="card:scd" />
    </div>
  );
}
