export function deriveOgTitle(opts: { pageTitle?: string | null; url?: string | null }): string {
  const title = opts.pageTitle?.trim();
  if (title) return title;
  if (opts.url) {
    try {
      return new URL(opts.url).hostname;
    } catch {
    }
  }
  return "vibecheck";
}

export function deriveOgDescription(opts: {
  headlineSummary?: string | null;
  safetyRationale?: string | null;
  url?: string | null;
}): string {
  const headline = opts.headlineSummary?.trim();
  if (headline) return headline;
  const rationale = opts.safetyRationale?.trim();
  if (rationale) return rationale;
  if (opts.url) {
    try {
      return `Vibecheck for: ${new URL(opts.url).hostname}`;
    } catch {
    }
  }
  return "Analyze URLs and PDFs for tone, claims, safety, and opinions.";
}
