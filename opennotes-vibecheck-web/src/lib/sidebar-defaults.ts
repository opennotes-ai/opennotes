import type { components } from "~/lib/generated-types";

export type SCDReport = components["schemas"]["SCDReport"];

export function makeEmptyScd(overrides: Partial<SCDReport> = {}): SCDReport {
  return {
    narrative: "",
    speaker_arcs: [],
    summary: "",
    tone_labels: [],
    per_speaker_notes: {},
    insufficient_conversation: true,
    upstream_stream_type: "unknown",
    observed_stream_type: "unknown",
    observed_confidence: 0,
    disagreement_rationale: "",
    ...overrides,
  };
}
