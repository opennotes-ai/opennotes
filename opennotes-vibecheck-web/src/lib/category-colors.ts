export type CategoryColor = "red" | "yellow" | "gray";

export const HARM_CONFIDENCE_THRESHOLD = 0.66;

export const HARM_CATEGORIES: ReadonlySet<string> = new Set([
  "adult",
  "death",
  "firearms & weapons",
  "harm & tragedy",
  "harassment",
  "hate",
  "illicit",
  "illicit drugs",
  "racy",
  "self-harm",
  "sexual",
  "violence",
  "violent",
  "war & conflict",
]);

export const SENSITIVE_CATEGORIES: ReadonlySet<string> = new Set([
  "finance",
  "health",
  "legal",
  "medical",
  "politics",
  "public safety",
  "religion & belief",
]);

function categoryKeys(name: string): string[] {
  const normalized = name.trim().toLowerCase();
  if (!normalized) return [];
  const root = normalized.split("/")[0]?.trim();
  return root && root !== normalized ? [normalized, root] : [normalized];
}

/**
 * Missing scores are treated as high confidence so bool-only provider flags
 * still render as harm labels when they match the explicit harm allowlist.
 */
export function categoryColor(
  name: string,
  score: number | undefined,
): CategoryColor {
  const keys = categoryKeys(name);
  if (keys.some((key) => SENSITIVE_CATEGORIES.has(key))) return "gray";
  if (keys.some((key) => HARM_CATEGORIES.has(key))) {
    const confidence = score ?? 1;
    return confidence > HARM_CONFIDENCE_THRESHOLD ? "red" : "yellow";
  }
  return "yellow";
}

export function categoryColorClasses(color: CategoryColor): string {
  switch (color) {
    case "red":
      return "bg-destructive/10 text-destructive";
    case "yellow":
      return "bg-amber-500/10 text-amber-600 dark:text-amber-500";
    case "gray":
      return "bg-muted text-muted-foreground";
  }
}
