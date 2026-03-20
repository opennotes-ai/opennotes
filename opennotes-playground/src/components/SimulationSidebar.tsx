import { For, createSignal } from "solid-js";
import { Sheet, SheetContent, SheetTitle } from "~/components/ui/sheet";
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

      <Sheet open={open()} onOpenChange={setOpen}>
        <SheetContent position="left" class="w-64 p-4">
          <div class="mb-4">
            <SheetTitle class="text-sm font-semibold">Sections</SheetTitle>
          </div>
          <SidebarNav onSectionClick={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
    </div>
  );
}
