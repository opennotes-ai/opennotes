import { For, createSignal, onMount, onCleanup } from "solid-js";
import { isServer } from "solid-js/web";
import { Sheet, SheetContent, SheetTitle } from "~/components/ui/sheet";
import { SECTIONS } from "./sections";
import { cn } from "~/lib/cn";

const [activeSection, setActiveSection] = createSignal<string>(SECTIONS[0].id);

function useScrollSpy() {
  if (isServer) return;

  const observerMap = new Map<string, IntersectionObserver>();

  function observeSection(id: string) {
    if (observerMap.has(id)) return;
    const el = document.getElementById(id);
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setActiveSection(id);
        }
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );
    observer.observe(el);
    observerMap.set(id, observer);
  }

  onMount(() => {
    function scanSections() {
      for (const section of SECTIONS) {
        observeSection(section.id);
      }
      if (observerMap.size < SECTIONS.length) {
        requestAnimationFrame(scanSections);
      }
    }
    scanSections();

    onCleanup(() => {
      for (const obs of observerMap.values()) obs.disconnect();
      observerMap.clear();
    });
  });
}

function SidebarNav(props: { onSectionClick?: () => void }) {
  return (
    <nav class="flex flex-col gap-0.5" aria-label="Page sections">
      <For each={SECTIONS}>
        {(section) => {
          const isActive = () => activeSection() === section.id;
          return (
            <button
              class={cn(
                "rounded px-2 py-1.5 text-left text-sm transition-colors",
                isActive()
                  ? "border-l-2 border-primary bg-muted pl-[calc(0.5rem-2px)] font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
              onClick={() => {
                document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth" });
                setActiveSection(section.id);
                props.onSectionClick?.();
              }}
            >
              {section.label}
            </button>
          );
        }}
      </For>
    </nav>
  );
}

export default function SimulationSidebar() {
  useScrollSpy();

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
