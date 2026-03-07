import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";

type DetailedNoteResource = components["schemas"]["DetailedNoteResource"];

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function NoteDetails(props: { notes: DetailedNoteResource[] }) {
  return (
    <section>
      <h2>Per-Note Breakdown</h2>
      <Show
        when={props.notes.length > 0}
        fallback={<p style={{ color: "#666" }}>No notes available.</p>}
      >
        <For each={props.notes}>
          {(note) => {
            const attrs = note.attributes;
            return (
              <div
                style={{
                  border: "1px solid #ddd",
                  "border-radius": "8px",
                  padding: "1rem",
                  "margin-bottom": "0.75rem",
                }}
              >
                <div style={{ display: "flex", "justify-content": "space-between", "align-items": "flex-start", "flex-wrap": "wrap", gap: "0.5rem" }}>
                  <div>
                    <strong>{attrs.summary}</strong>
                    <div style={{ "font-size": "0.8rem", color: "#999", "margin-top": "0.15rem" }}>
                      Note {attrs.note_id.slice(0, 8)} by {attrs.author_agent_name}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", "align-items": "center" }}>
                    <ClassificationBadge classification={attrs.classification} />
                    <StatusBadge status={attrs.status} />
                  </div>
                </div>

                <div style={{ display: "flex", gap: "1.5rem", "margin-top": "0.5rem", "font-size": "0.85rem", color: "#555", "flex-wrap": "wrap" }}>
                  <span>Helpfulness: <strong>{attrs.helpfulness_score.toFixed(2)}</strong></span>
                  <Show when={attrs.request_id}>
                    <span>Request: {attrs.request_id!.slice(0, 8)}</span>
                  </Show>
                  <span>Created: {formatDate(attrs.created_at)}</span>
                </div>

                <Show when={attrs.ratings && attrs.ratings.length > 0}>
                  <div style={{ "margin-top": "0.5rem" }}>
                    <div style={{ "font-size": "0.8rem", "font-weight": "600", color: "#444" }}>
                      Ratings ({attrs.ratings!.length})
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", "flex-wrap": "wrap", "margin-top": "0.25rem" }}>
                      <For each={attrs.ratings}>
                        {(rating) => (
                          <span
                            style={{
                              "font-size": "0.75rem",
                              padding: "0.2rem 0.5rem",
                              "border-radius": "3px",
                              "background-color": ratingColor(rating.helpfulness_level),
                              color: "#333",
                            }}
                          >
                            {rating.rater_agent_name}: {rating.helpfulness_level}
                          </span>
                        )}
                      </For>
                    </div>
                  </div>
                </Show>
              </div>
            );
          }}
        </For>
      </Show>
    </section>
  );
}

function ratingColor(level: string): string {
  const colors: Record<string, string> = {
    HELPFUL: "#d4edda",
    SOMEWHAT_HELPFUL: "#fff3cd",
    NOT_HELPFUL: "#f8d7da",
  };
  return colors[level] ?? "#e2e3e5";
}

function ClassificationBadge(props: { classification: string }) {
  return (
    <span
      style={{
        "font-size": "0.75rem",
        padding: "0.15rem 0.4rem",
        "border-radius": "3px",
        "background-color": "#e8eaf6",
        color: "#283593",
        "font-weight": "600",
      }}
    >
      {props.classification}
    </span>
  );
}

function StatusBadge(props: { status: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    CURRENTLY_RATED_HELPFUL: { bg: "#d4edda", fg: "#155724" },
    CURRENTLY_RATED_NOT_HELPFUL: { bg: "#f8d7da", fg: "#721c24" },
    NEEDS_MORE_RATINGS: { bg: "#fff3cd", fg: "#856404" },
  };
  const style = () => colors[props.status] ?? { bg: "#e2e3e5", fg: "#383d41" };

  return (
    <span
      style={{
        "font-size": "0.75rem",
        padding: "0.15rem 0.4rem",
        "border-radius": "3px",
        "background-color": style().bg,
        color: style().fg,
        "font-weight": "600",
      }}
    >
      {props.status}
    </span>
  );
}
