export const SECTIONS = [
  { id: "agents", label: "Agents" },
  { id: "notes-ratings", label: "Notes & Ratings" },
  { id: "scoring-analysis", label: "Scoring & Analysis" },
  { id: "note-details", label: "Note Details" },
  { id: "sim-channel", label: "Chat Channel" },
] as const;

export type SectionId = (typeof SECTIONS)[number]["id"];
