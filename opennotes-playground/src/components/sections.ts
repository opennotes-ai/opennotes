export const SECTIONS = [
  { id: "agents", label: "The Agents" },
  { id: "notes-ratings", label: "Notes & Ratings" },
  { id: "scoring-analysis", label: "Scoring & Consensus" },
  { id: "note-details", label: "Note Details" },
  { id: "sim-channel", label: "The Conversation" },
] as const;

export type SectionId = (typeof SECTIONS)[number]["id"];
