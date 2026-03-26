export const SEMANTIC_COLORS: Record<string, string> = {
  HELPFUL: "#2a9d6e",
  SOMEWHAT_HELPFUL: "#4a7fd4",
  NOT_HELPFUL: "#d4874a",

  CURRENTLY_RATED_HELPFUL: "#2a9d6e",
  CURRENTLY_RATED_NOT_HELPFUL: "#d4874a",
  NEEDS_MORE_RATINGS: "#9a5eb8",

  WRITE_NOTE: "#2a9d6e",
  RATE_NOTE: "#4a7fd4",
  PASS_TURN: "#9a5eb8",
  REQUEST_REPLY: "#d4874a",
  SKIP: "#9a9435",
};

export function getSemanticColor(key: string): string | undefined {
  return SEMANTIC_COLORS[key];
}
