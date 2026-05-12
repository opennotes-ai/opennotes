import { describe, it, expect, beforeEach } from "vitest";
import { createRoot } from "solid-js";
import { createHighlightsStore, type HighlightItem } from "./highlights-store";

function makeItem(id: string, source: string, overrides: Partial<HighlightItem> = {}): HighlightItem {
  return { id, source, title: `Title ${id}`, ...overrides };
}

describe("createHighlightsStore", () => {
  describe("push", () => {
    it("starts empty", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        expect(store.items()).toEqual([]);
        dispose();
      });
    });

    it("appends items to an empty store", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        const items = [makeItem("a", "src1"), makeItem("b", "src1")];
        store.push("src1", items);
        expect(store.items()).toEqual(items);
        dispose();
      });
    });

    it("appends new items to existing items for same source", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src1", [makeItem("b", "src1")]);
        const ids = store.items().map((i) => i.id);
        expect(ids).toEqual(["a", "b"]);
        dispose();
      });
    });

    it("appends items from multiple sources in insertion order", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src2", [makeItem("b", "src2")]);
        store.push("src1", [makeItem("c", "src1")]);
        const ids = store.items().map((i) => i.id);
        expect(ids).toEqual(["a", "c", "b"]);
        dispose();
      });
    });

    it("replaces an existing item in-place when id collides within source", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1", { title: "original" })]);
        store.push("src1", [makeItem("a", "src1", { title: "updated" })]);
        const items = store.items();
        expect(items).toHaveLength(1);
        expect(items[0].title).toBe("updated");
        dispose();
      });
    });

    it("preserves insertion order when deduping: updated item stays at original index", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1"), makeItem("b", "src1")]);
        store.push("src1", [makeItem("a", "src1", { title: "updated" })]);
        const ids = store.items().map((i) => i.id);
        expect(ids).toEqual(["a", "b"]);
        dispose();
      });
    });
  });

  describe("replaceForSource", () => {
    it("replaces only the target source list", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src2", [makeItem("b", "src2")]);
        store.replaceForSource("src1", [makeItem("c", "src1"), makeItem("d", "src1")]);
        const ids = store.items().map((i) => i.id);
        expect(ids).toContain("c");
        expect(ids).toContain("d");
        expect(ids).toContain("b");
        expect(ids).not.toContain("a");
        dispose();
      });
    });

    it("preserves other sources untouched", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src2", [makeItem("b", "src2")]);
        store.push("src3", [makeItem("c", "src3")]);
        store.replaceForSource("src2", [makeItem("x", "src2")]);
        const ids = store.items().map((i) => i.id);
        expect(ids).toContain("a");
        expect(ids).toContain("x");
        expect(ids).toContain("c");
        expect(ids).not.toContain("b");
        dispose();
      });
    });

    it("can replace with an empty list (removes all items for that source)", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src2", [makeItem("b", "src2")]);
        store.replaceForSource("src1", []);
        const ids = store.items().map((i) => i.id);
        expect(ids).toEqual(["b"]);
        dispose();
      });
    });

    it("maintains source insertion order after replace", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src2", [makeItem("b", "src2")]);
        store.replaceForSource("src1", [makeItem("z", "src1")]);
        const ids = store.items().map((i) => i.id);
        expect(ids).toEqual(["z", "b"]);
        dispose();
      });
    });
  });

  describe("clear", () => {
    it("empties the entire store", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.push("src2", [makeItem("b", "src2")]);
        store.clear();
        expect(store.items()).toEqual([]);
        dispose();
      });
    });

    it("allows pushing after clear", () => {
      createRoot((dispose) => {
        const store = createHighlightsStore();
        store.push("src1", [makeItem("a", "src1")]);
        store.clear();
        store.push("src2", [makeItem("b", "src2")]);
        expect(store.items()).toHaveLength(1);
        expect(store.items()[0].id).toBe("b");
        dispose();
      });
    });
  });
});
