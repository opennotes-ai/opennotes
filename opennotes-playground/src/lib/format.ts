// Playground-local display formatters. `humanizeLabel` + `LABEL_MAP` are
// Community Notes / simulation-state domain-coupled (rating enums, sim
// status keywords) and live here rather than in @opennotes/ui so the
// shared package stays domain-neutral. Generic UUID/proquint/ID badge
// helpers moved to @opennotes/ui/utils/ids instead.
const LABEL_MAP: Record<string, string> = {
  SOMEWHAT_HELPFUL: "Somewhat Helpful",
  HELPFUL: "Helpful",
  NOT_HELPFUL: "Not Helpful",
  CURRENTLY_RATED_HELPFUL: "Currently Rated Helpful",
  CURRENTLY_RATED_NOT_HELPFUL: "Currently Rated Not Helpful",
  NEEDS_MORE_RATINGS: "Needs More Ratings",
  NOT_MISLEADING: "Not Misleading",
  MISINFORMED_OR_POTENTIALLY_MISLEADING: "Potentially Misleading",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  paused: "Paused",
  pending: "Pending",
  active: "Active",
  idle: "Idle",
  error: "Error",
};

export function humanizeLabel(raw: string): string {
  return (
    LABEL_MAP[raw] ??
    raw
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getMetric(
  metrics: Record<string, unknown> | null | undefined,
  key: string,
): string {
  if (!metrics || !(key in metrics)) return "N/A";
  const val = metrics[key];
  if (val == null) return "N/A";
  return String(val);
}

// Re-export generic ID formatters so existing playground call sites that
// import from ~/lib/format don't need to know about the split.
export {
  formatIdBadgeLabel,
  formatIdBadgeTooltip,
  isUuidLike,
  proquintToHexSuffix,
  resolveAnchorId,
  truncateId,
} from "@opennotes/ui/utils";
