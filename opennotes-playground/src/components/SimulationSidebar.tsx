import { For } from "solid-js";

const SECTIONS = [
  { id: "metadata", label: "Metadata" },
  { id: "note-quality", label: "Note Quality" },
  { id: "rating-distribution", label: "Rating Distribution" },
  { id: "consensus-metrics", label: "Consensus Metrics" },
  { id: "scoring-coverage", label: "Scoring Coverage" },
  { id: "agent-behaviors", label: "Agent Behaviors" },
  { id: "per-note-breakdown", label: "Per-Note Breakdown" },
];

export default function SimulationSidebar() {
  return (
    <nav class="sticky top-8 flex flex-col gap-1" aria-label="Page sections">
      <For each={SECTIONS}>
        {(section) => (
          <button
            class="rounded px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            onClick={() =>
              document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth" })
            }
          >
            {section.label}
          </button>
        )}
      </For>
    </nav>
  );
}
