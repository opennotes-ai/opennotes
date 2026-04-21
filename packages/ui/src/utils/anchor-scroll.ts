import { resolveAnchorId } from "./ids";

export type AnchorTarget = {
  type: "note" | "agent" | "request";
  id: string;
};

export function parseFragment(
  hash: string,
  items: Array<{ id: string }>,
  type: string,
): AnchorTarget | null {
  if (!hash || !hash.startsWith("#")) return null;
  const raw = hash.slice(1);
  const prefix = `${type}-`;
  if (!raw.startsWith(prefix)) return null;
  const resolved = resolveAnchorId(raw, items, type);
  if (!resolved) return null;
  return { type: type as AnchorTarget["type"], id: resolved };
}

export function findPageForItem<T>(
  items: T[],
  targetId: string,
  pageSize: number,
  getId: (item: T) => string,
): number {
  const index = items.findIndex((item) => getId(item) === targetId);
  if (index === -1) return 1;
  return Math.floor(index / pageSize) + 1;
}

export function scrollToAndHighlight(elementId: string): void {
  requestAnimationFrame(() => {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("anchor-highlight");
    setTimeout(() => el.classList.remove("anchor-highlight"), 2000);
  });
}
