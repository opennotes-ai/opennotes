export const SITE_ORIGIN = "https://vibecheck.opennotes.ai";

export function siteUrl(path: string): string {
  if (!path.startsWith("/")) {
    return `${SITE_ORIGIN}/${path}`;
  }
  return `${SITE_ORIGIN}${path}`;
}
