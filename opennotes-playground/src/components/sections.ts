export const SECTIONS = [
  { id: "metadata", label: "Metadata" },
  { id: "note-quality", label: "Note Quality" },
  { id: "rating-distribution", label: "Rating Distribution" },
  { id: "consensus-metrics", label: "Consensus Metrics" },
  { id: "scoring-coverage", label: "Scoring Coverage" },
  { id: "agent-behaviors", label: "Agent Behaviors" },
  { id: "per-note-breakdown", label: "Per-Note Breakdown" },
] as const;

export type SectionId = (typeof SECTIONS)[number]["id"];
