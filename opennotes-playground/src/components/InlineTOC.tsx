import { For } from "solid-js";
import { SECTIONS, type SectionId } from "./sections";

interface InlineTOCProps {
  loadedSections: Set<SectionId>;
  onSectionClick: (id: SectionId) => void;
}

export default function InlineTOC(props: InlineTOCProps) {
  return (
    <nav class="mt-6 rounded-lg border border-border bg-card p-4" aria-label="Table of contents">
      <h2 class="mb-3 text-sm font-semibold text-foreground">Sections</h2>
      <ul class="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <For each={SECTIONS.filter((s) => s.id !== "metadata")}>
          {(section) => (
            <li>
              <button
                class="w-full rounded px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                classList={{ "font-medium text-foreground": props.loadedSections.has(section.id) }}
                onClick={() => props.onSectionClick(section.id)}
              >
                {section.label}
              </button>
            </li>
          )}
        </For>
      </ul>
    </nav>
  );
}
