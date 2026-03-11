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

const UNKNOWN_ID_LABEL = "<Unspecified>";
const UUID_LIKE_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const PROQUINT_CONSONANTS = "bdfghjklmnprstvz";
const PROQUINT_VOWELS = "aiou";

function encodeProquintWord(word: number): string {
  return [
    PROQUINT_CONSONANTS[word & 0x0f],
    PROQUINT_VOWELS[(word >> 4) & 0x03],
    PROQUINT_CONSONANTS[(word >> 6) & 0x0f],
    PROQUINT_VOWELS[(word >> 10) & 0x03],
    PROQUINT_CONSONANTS[(word >> 12) & 0x0f],
  ].join("");
}

function uuidSuffixToProquint(uuid: string): string {
  const hex = uuid.replace(/-/g, "").slice(-8);
  const upperWord = Number.parseInt(hex.slice(0, 4), 16);
  const lowerWord = Number.parseInt(hex.slice(4), 16);
  return `${encodeProquintWord(upperWord)}-${encodeProquintWord(lowerWord)}`;
}

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

export function isUuidLike(id: string | null | undefined): id is string {
  return typeof id === "string" && UUID_LIKE_RE.test(id);
}

export function formatIdBadgeLabel(id: string | null | undefined): string {
  if (id == null) return UNKNOWN_ID_LABEL;
  if (!isUuidLike(id)) return id;
  return uuidSuffixToProquint(id);
}

export function formatIdBadgeTooltip(id: string | null | undefined): string {
  if (id == null) return UNKNOWN_ID_LABEL;
  if (!isUuidLike(id)) return id;
  const label = formatIdBadgeLabel(id);
  return `${label}\n${id}`;
}

export function truncateId(id: string | null | undefined): string {
  if (!id) return "N/A";
  return id.slice(0, 8);
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
