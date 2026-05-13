import { describe, it, expect } from "vitest";
import { createRoot, createSignal } from "solid-js";
import {
  ALL_LABELS,
  createSidebarStore,
  type SectionGroupLabel,
} from "./sidebar-store";

describe("ALL_LABELS", () => {
  it("includes the promoted Sentiments group and renamed Opinions group", () => {
    expect(ALL_LABELS).toContain("Sentiments");
    expect(ALL_LABELS).toContain("Opinions");
    expect(ALL_LABELS).not.toContain("Opinions/sentiments");
  });

  it("orders groups Safety, Sentiments, Tone/dynamics, Facts/claims, Opinions", () => {
    expect([...ALL_LABELS]).toEqual([
      "Safety",
      "Sentiments",
      "Tone/dynamics",
      "Facts/claims",
      "Opinions",
    ]);
  });
});

describe("createSidebarStore", () => {
  it("all groups start open when defaultOpen is not specified", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      const labels: SectionGroupLabel[] = [
        "Safety",
        "Sentiments",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions",
      ];
      for (const label of labels) {
        expect(store.isOpen(label)).toBe(true);
      }
      dispose();
    });
  });

  it("non-sticky groups start closed when defaultOpen is false", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: () => false });
      expect(store.isOpen("Safety")).toBe(false);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Facts/claims")).toBe(false);
      expect(store.isOpen("Opinions")).toBe(false);
      dispose();
    });
  });

  it("Sentiments ignores defaultOpen=false and stays open at init", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: () => false });
      expect(store.isOpen("Sentiments")).toBe(true);
      dispose();
    });
  });

  it("setOpen(label, false) closes only the targeted group", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.setOpen("Safety", false);
      expect(store.isOpen("Safety")).toBe(false);
      expect(store.isOpen("Sentiments")).toBe(true);
      expect(store.isOpen("Tone/dynamics")).toBe(true);
      expect(store.isOpen("Facts/claims")).toBe(true);
      expect(store.isOpen("Opinions")).toBe(true);
      dispose();
    });
  });

  it("setOpen(label, true) opens only the targeted group", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: () => false });
      store.setOpen("Safety", true);
      expect(store.isOpen("Safety")).toBe(true);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Facts/claims")).toBe(false);
      expect(store.isOpen("Opinions")).toBe(false);
      // Sentiments is sticky-open regardless of defaultOpen
      expect(store.isOpen("Sentiments")).toBe(true);
      dispose();
    });
  });

  it("isolateGroup closes non-sticky non-target groups, keeps target open, preserves STICKY_OPEN_LABELS", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.isolateGroup("Safety");
      expect(store.isOpen("Safety")).toBe(true);
      // Sentiments is sticky-open: isolating another group must NOT close it
      // (parent TASK-1633 AC #2 — Sentiment stays visible when Opinions/other
      // top-level cards collapse, including via WeatherReport focus actions).
      expect(store.isOpen("Sentiments")).toBe(true);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Facts/claims")).toBe(false);
      expect(store.isOpen("Opinions")).toBe(false);
      dispose();
    });
  });

  it("isolateGroup(\"Sentiments\") still closes the other four groups", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.isolateGroup("Sentiments");
      expect(store.isOpen("Sentiments")).toBe(true);
      expect(store.isOpen("Safety")).toBe(false);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Facts/claims")).toBe(false);
      expect(store.isOpen("Opinions")).toBe(false);
      dispose();
    });
  });

  it("isolateGroup works when target group was previously closed (Sentiments still sticky-open)", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: () => false });
      store.isolateGroup("Facts/claims");
      expect(store.isOpen("Facts/claims")).toBe(true);
      expect(store.isOpen("Safety")).toBe(false);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Opinions")).toBe(false);
      // Sentiments stays open through isolateGroup (sticky)
      expect(store.isOpen("Sentiments")).toBe(true);
      dispose();
    });
  });

  it("highlightedGroup returns null initially", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      expect(store.highlightedGroup()).toBe(null);
      dispose();
    });
  });

  it("setHighlightedGroup causes highlightedGroup to return the new value", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.setHighlightedGroup("Safety");
      expect(store.highlightedGroup()).toBe("Safety");
      dispose();
    });
  });

  it("setHighlightedGroup accepts the promoted Sentiments label", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.setHighlightedGroup("Sentiments");
      expect(store.highlightedGroup()).toBe("Sentiments");
      dispose();
    });
  });

  it("setHighlightedGroup can clear the highlight with null", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.setHighlightedGroup("Safety");
      store.setHighlightedGroup(null);
      expect(store.highlightedGroup()).toBe(null);
      dispose();
    });
  });

  it("isOpen is reactive — changes via setOpen are visible in the same root", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      expect(store.isOpen("Safety")).toBe(true);
      store.setOpen("Safety", false);
      expect(store.isOpen("Safety")).toBe(false);
      store.setOpen("Safety", true);
      expect(store.isOpen("Safety")).toBe(true);
      dispose();
    });
  });

  it("reset() restores all groups to defaultOpen=true when no opts given", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.setOpen("Safety", false);
      store.setOpen("Tone/dynamics", false);
      store.reset();
      const labels: SectionGroupLabel[] = [
        "Safety",
        "Sentiments",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions",
      ];
      for (const label of labels) {
        expect(store.isOpen(label)).toBe(true);
      }
      dispose();
    });
  });

  it("reset() restores non-sticky groups to defaultOpen=false; Sentiments stays open", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: () => false });
      store.setOpen("Safety", true);
      store.setOpen("Facts/claims", true);
      store.setOpen("Sentiments", false);
      store.reset();
      const collapsed: SectionGroupLabel[] = [
        "Safety",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions",
      ];
      for (const label of collapsed) {
        expect(store.isOpen(label)).toBe(false);
      }
      expect(store.isOpen("Sentiments")).toBe(true);
      dispose();
    });
  });

  it("reset() applies the latest reactive defaultOpen to non-sticky groups; Sentiments stays open", () => {
    createRoot((dispose) => {
      const [defaultOpen, setDefaultOpen] = createSignal(true);
      const store = createSidebarStore({ defaultOpen });
      expect(store.isOpen("Safety")).toBe(true);

      setDefaultOpen(false);
      store.setOpen("Safety", true);
      store.setOpen("Tone/dynamics", true);
      store.setOpen("Sentiments", false);
      store.reset();

      const collapsed: SectionGroupLabel[] = [
        "Safety",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions",
      ];
      for (const label of collapsed) {
        expect(store.isOpen(label)).toBe(false);
      }
      expect(store.isOpen("Sentiments")).toBe(true);
      dispose();
    });
  });
});
