export type BlockingFamily = "reddit" | "linkedin";

export type BlockingHostMatch =
  | { match: true; host: string; family: BlockingFamily }
  | { match: false };

export const BLOCKING_HOST_FAMILIES: readonly {
  family: BlockingFamily;
  root: string;
}[] = [
  { family: "reddit", root: "reddit.com" },
  { family: "linkedin", root: "linkedin.com" },
];

// URL() host parsing applies normalization (e.g., case-folding and IDN/punycode
// handling); this utility relies on that behavior.
function normalizeHost(host: string): string | null {
  const lower = host.toLowerCase();
  if (!lower) {
    return null;
  }

  if (!lower.endsWith(".")) {
    return lower;
  }

  if (lower.endsWith("..")) {
    return null;
  }

  return lower.slice(0, -1);
}

export function isBlockingHost(input: string | URL): BlockingHostMatch {
  const parsedUrl =
    input instanceof URL
      ? input
      : (() => {
          try {
            return new URL(input);
          } catch {
            return null;
          }
        })();

  if (
    parsedUrl === null ||
    (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:")
  ) {
    return { match: false };
  }

  const normalizedHost = parsedUrl.hostname
    ? normalizeHost(parsedUrl.hostname)
    : null;
  if (!normalizedHost) {
    return { match: false };
  }

  for (const { family, root } of BLOCKING_HOST_FAMILIES) {
    if (normalizedHost === root || normalizedHost.endsWith(`.${root}`)) {
      return { match: true, host: normalizedHost, family };
    }
  }

  return { match: false };
}
