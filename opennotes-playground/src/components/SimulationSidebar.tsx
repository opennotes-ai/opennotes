import { For } from "solid-js";
import { SECTIONS } from "./sections";

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
