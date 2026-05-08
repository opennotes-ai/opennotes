import { describe, it, expect } from "vitest";
import { render } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import NoteDetails from "./NoteDetails";

type DetailedNoteResource = components["schemas"]["DetailedNoteResource"];

function makeNote(overrides?: Partial<DetailedNoteResource["attributes"]>): DetailedNoteResource {
  return {
    type: "notes",
    id: "note-1",
    attributes: {
      note_id: "note-1",
      author_agent_id: "agent-1",
      author_agent_name: "Agent One",
      summary: "This claim is misleading because reasons.",
      classification: "MISINFORMED_OR_POTENTIALLY_MISLEADING",
      status: "CURRENTLY_RATED_HELPFUL",
      helpfulness_score: 0.42,
      created_at: "2026-01-01T00:00:00Z",
      ratings: [],
      request_id: "req-1",
      message_metadata: null,
      ...overrides,
    } as DetailedNoteResource["attributes"],
  };
}

describe("NoteDetails", () => {
  it("renders each note inside a Card-styled container with rounded-md, border, bg-card and p-4", () => {
    const notes = [makeNote()];
    const { container } = render(() => (
      <NoteDetails
        notes={notes}
        currentTier="tier_0"
        sortBy="count"
        onSortChange={() => {}}
        filterClassification={[]}
        filterStatus={[]}
        onFilterChange={() => {}}
      />
    ));

    const noteCard = container.querySelector('[data-testid="note-card"]');
    expect(noteCard).not.toBeNull();
    expect(noteCard?.tagName.toLowerCase()).toBe("div");
    const cls = noteCard?.className ?? "";
    expect(cls).toContain("rounded-md");
    expect(cls).toMatch(/\bborder-border\b/);
    expect(cls).toContain("bg-card");
    expect(cls).toContain("p-4");
    expect(cls).not.toContain("shadow-none");
    expect(cls).not.toContain("shadow-sm");
  });
});
