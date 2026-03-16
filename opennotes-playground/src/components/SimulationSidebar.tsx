import { For, createSignal } from "solid-js";
import { Dialog } from "@kobalte/core/dialog";
import { SECTIONS } from "./sections";

function SidebarNav(props: { onSectionClick?: () => void }) {
  return (
    <nav class="flex flex-col gap-1" aria-label="Page sections">
      <For each={SECTIONS}>
        {(section) => (
          <button
            class="rounded px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            onClick={() => {
              document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth" });
              props.onSectionClick?.();
            }}
          >
            {section.label}
          </button>
        )}
      </For>
    </nav>
  );
}

export default function SimulationSidebar() {
  return (
    <aside class="hidden w-48 shrink-0 lg:block">
      <div class="sticky top-8">
        <SidebarNav />
      </div>
    </aside>
  );
}

export function MobileSidebarToggle() {
  const [open, setOpen] = createSignal(false);

  return (
    <div class="lg:hidden">
      <button
        class="rounded-md border border-border p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
      >
        <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <Dialog open={open()} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay class="fixed inset-0 z-40 bg-black/50" />
          <Dialog.Content class="fixed inset-y-0 left-0 z-50 w-64 bg-background p-4 shadow-lg">
            <div class="mb-4 flex items-center justify-between">
              <Dialog.Title class="text-sm font-semibold">Sections</Dialog.Title>
              <Dialog.CloseButton class="rounded p-1 hover:bg-muted">
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </Dialog.CloseButton>
            </div>
            <SidebarNav onSectionClick={() => setOpen(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog>
    </div>
  );
}
