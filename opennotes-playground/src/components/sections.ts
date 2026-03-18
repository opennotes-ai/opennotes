export const SECTIONS = [
  { id: "agents", label: "Agents" },
  { id: "notes-ratings", label: "Notes & Ratings" },
  { id: "note-details", label: "Note Details" },
  { id: "scoring-analysis", label: "Scoring & Analysis" },
] as const;

export type SectionId = (typeof SECTIONS)[number]["id"];
