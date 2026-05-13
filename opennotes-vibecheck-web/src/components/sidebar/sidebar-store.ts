import { createSignal } from "solid-js";

export const ALL_LABELS = [
  "Safety",
  "Tone/dynamics",
  "Facts/claims",
  "Opinions/sentiments",
] as const;

export type SectionGroupLabel = (typeof ALL_LABELS)[number];

export interface SidebarStore {
  isOpen: (label: SectionGroupLabel) => boolean;
  setOpen: (label: SectionGroupLabel, open: boolean) => void;
  isolateGroup: (label: SectionGroupLabel) => void;
  reset: () => void;
  highlightedGroup: () => SectionGroupLabel | null;
  setHighlightedGroup: (label: SectionGroupLabel | null) => void;
}

export function createSidebarStore(opts?: { defaultOpen?: () => boolean }): SidebarStore {
  const defaultOpen = () => opts?.defaultOpen?.() ?? true;

  const signals = new Map<SectionGroupLabel, ReturnType<typeof createSignal<boolean>>>(
    ALL_LABELS.map((label) => [label, createSignal(defaultOpen())]),
  );

  const [highlightedGroup, setHighlightedGroup] = createSignal<SectionGroupLabel | null>(null);

  function isOpen(label: SectionGroupLabel): boolean {
    return signals.get(label)![0]();
  }

  function setOpen(label: SectionGroupLabel, open: boolean): void {
    signals.get(label)![1](open);
  }

  function isolateGroup(target: SectionGroupLabel): void {
    for (const label of ALL_LABELS) {
      signals.get(label)![1](label === target);
    }
  }

  function reset(): void {
    for (const label of ALL_LABELS) {
      signals.get(label)![1](defaultOpen());
    }
  }

  return { isOpen, setOpen, isolateGroup, reset, highlightedGroup, setHighlightedGroup };
}
