import { createSignal } from "solid-js";

export type HighlightSeverity = "info" | "warn" | "critical";

export interface HighlightItem {
  id: string;
  source: string;
  title: string;
  detail?: string;
  severity?: HighlightSeverity;
}

export interface HighlightsStore {
  items: () => HighlightItem[];
  push(source: string, items: HighlightItem[]): void;
  replaceForSource(source: string, items: HighlightItem[]): void;
  clear(): void;
}

export function createHighlightsStore(): HighlightsStore {
  const sourceMap = new Map<string, HighlightItem[]>();
  const [tick, setTick] = createSignal(0);

  function items(): HighlightItem[] {
    tick();
    const result: HighlightItem[] = [];
    for (const list of sourceMap.values()) {
      result.push(...list);
    }
    return result;
  }

  function push(source: string, incoming: HighlightItem[]): void {
    const existing = sourceMap.get(source) ?? [];
    for (const item of incoming) {
      const idx = existing.findIndex((e) => e.id === item.id);
      if (idx >= 0) {
        existing[idx] = item;
      } else {
        existing.push(item);
      }
    }
    sourceMap.set(source, existing);
    setTick((n) => n + 1);
  }

  function replaceForSource(source: string, incoming: HighlightItem[]): void {
    sourceMap.set(source, [...incoming]);
    setTick((n) => n + 1);
  }

  function clear(): void {
    sourceMap.clear();
    setTick((n) => n + 1);
  }

  return { items, push, replaceForSource, clear };
}
