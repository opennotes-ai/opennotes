import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import UtteranceRef from "../UtteranceRef";
import SubjectiveReport from "./SubjectiveReport";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type OpinionsHighlightsReport = components["schemas"]["OpinionsHighlightsReport"];
type OpinionsHighlight = components["schemas"]["OpinionsHighlight"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];

export interface HighlightsReportProps {
  report: OpinionsHighlightsReport | null;
  legacySubjectiveClaims?: SubjectiveClaim[];
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
}

export default function HighlightsReport(props: HighlightsReportProps) {
  const highlights = (): OpinionsHighlight[] => props.report?.highlights ?? [];
  const legacySubjectiveClaims = (): SubjectiveClaim[] =>
    props.legacySubjectiveClaims ?? [];

  return (
    <Show
      when={props.report}
      fallback={
        <Show when={legacySubjectiveClaims().length > 0}>
          <SubjectiveReport
            claims={legacySubjectiveClaims()}
            onUtteranceClick={props.onUtteranceClick}
            canJumpToUtterance={props.canJumpToUtterance}
          />
        </Show>
      }
    >
      {(report) => (
        <div data-testid="report-opinions_sentiments__highlights" class="relative space-y-2">
          <div class="flex items-center gap-1.5">
            <p class="text-[11px] text-muted-foreground">
              {highlights().length} highlight
              {highlights().length === 1 ? "" : "s"}
            </p>
            <Show when={report().fallback_engaged}>
              <span class="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                Limited evidence
              </span>
            </Show>
          </div>
          <Show
            when={highlights().length > 0}
            fallback={
              <p class="text-xs text-muted-foreground">
                No notable highlights cleared the threshold.
              </p>
            }
          >
            <ul class="space-y-1.5">
              <For each={highlights()}>
                {(highlight) => {
                  const primaryId = highlight.cluster.utterance_ids?.[0];
                  return (
                    <li data-testid="highlight-item" class="text-xs">
                      <ExpandableText
                        text={highlight.cluster.canonical_text}
                        lines={2}
                        class="text-foreground"
                        testId="highlight-text"
                      />
                      <div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                        <span class="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5">
                          {highlight.cluster.author_count} author
                          {highlight.cluster.author_count === 1 ? "" : "s"}
                        </span>
                        <span class="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5">
                          {highlight.cluster.occurrence_count} occurrence
                          {highlight.cluster.occurrence_count === 1 ? "" : "s"}
                        </span>
                        <Show when={primaryId}>
                          {(id) => (
                            <UtteranceRef
                              utteranceId={String(id())}
                              label={`turn ${id()}`}
                              onClick={
                                props.onUtteranceClick ?? (() => undefined)
                              }
                              disabled={
                                !props.canJumpToUtterance ||
                                !props.onUtteranceClick
                              }
                              testId="highlight-utterance-ref"
                            />
                          )}
                        </Show>
                      </div>
                    </li>
                  );
                }}
              </For>
            </ul>
          </Show>
          <FeedbackBell bell_location="card:highlights" />
        </div>
      )}
    </Show>
  );
}
