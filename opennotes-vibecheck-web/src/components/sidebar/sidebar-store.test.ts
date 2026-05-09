import { describe, it, expect } from "vitest";
import { createRoot } from "solid-js";
import { createSidebarStore, type SectionGroupLabel } from "./sidebar-store";

describe("createSidebarStore", () => {
  it("all groups start open when defaultOpen is not specified", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      const labels: SectionGroupLabel[] = [
        "Safety",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions/sentiments",
      ];
      for (const label of labels) {
        expect(store.isOpen(label)).toBe(true);
      }
      dispose();
    });
  });

  it("all groups start closed when defaultOpen is false", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: false });
      const labels: SectionGroupLabel[] = [
        "Safety",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions/sentiments",
      ];
      for (const label of labels) {
        expect(store.isOpen(label)).toBe(false);
      }
      dispose();
    });
  });

  it("setOpen(label, false) closes only the targeted group", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.setOpen("Safety", false);
      expect(store.isOpen("Safety")).toBe(false);
      expect(store.isOpen("Tone/dynamics")).toBe(true);
      expect(store.isOpen("Facts/claims")).toBe(true);
      expect(store.isOpen("Opinions/sentiments")).toBe(true);
      dispose();
    });
  });

  it("setOpen(label, true) opens only the targeted group", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: false });
      store.setOpen("Safety", true);
      expect(store.isOpen("Safety")).toBe(true);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Facts/claims")).toBe(false);
      expect(store.isOpen("Opinions/sentiments")).toBe(false);
      dispose();
    });
  });

  it("isolateGroup closes all non-target groups and leaves target open", () => {
    createRoot((dispose) => {
      const store = createSidebarStore();
      store.isolateGroup("Safety");
      expect(store.isOpen("Safety")).toBe(true);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Facts/claims")).toBe(false);
      expect(store.isOpen("Opinions/sentiments")).toBe(false);
      dispose();
    });
  });

  it("isolateGroup works when target group was previously closed", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: false });
      store.isolateGroup("Facts/claims");
      expect(store.isOpen("Facts/claims")).toBe(true);
      expect(store.isOpen("Safety")).toBe(false);
      expect(store.isOpen("Tone/dynamics")).toBe(false);
      expect(store.isOpen("Opinions/sentiments")).toBe(false);
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
        "Tone/dynamics",
        "Facts/claims",
        "Opinions/sentiments",
      ];
      for (const label of labels) {
        expect(store.isOpen(label)).toBe(true);
      }
      dispose();
    });
  });

  it("reset() restores all groups to defaultOpen=false when store was created with collapseAllByDefault", () => {
    createRoot((dispose) => {
      const store = createSidebarStore({ defaultOpen: false });
      store.setOpen("Safety", true);
      store.setOpen("Facts/claims", true);
      store.reset();
      const labels: SectionGroupLabel[] = [
        "Safety",
        "Tone/dynamics",
        "Facts/claims",
        "Opinions/sentiments",
      ];
      for (const label of labels) {
        expect(store.isOpen(label)).toBe(false);
      }
      dispose();
    });
  });
});
