import type { OverallDecision } from "~/components/overall/OverallRecommendationCard";
import type { JobState } from "~/lib/api-client.server";

export type AnalyzeTitleLifecycle =
  | "extracting"
  | "analyzing"
  | "recommending"
  | "partial analysis"
  | "failed analysis";

const TITLE_PREFIX = "vibecheck";
const TITLE_SEPARATOR = " - ";
const DEFAULT_ANALYZED_TITLE = "Untitled analysis";
const DEFAULT_TITLE_SEGMENT_MAX = 100;

const ACTIVITY_LIFECYCLES: Record<string, AnalyzeTitleLifecycle> = {
  "Converting images to PDF": "extracting",
  "Extracting page content": "extracting",
  "Saving page content": "extracting",
  "Preparing analysis": "analyzing",
  "Running section analyses": "analyzing",
  "Computing safety guidance": "recommending",
  "Writing summary": "recommending",
  "Writing weather report": "recommending",
  "Writing overall recommendation": "recommending",
  "Finalizing results": "recommending",
  "Running analysis": "analyzing",
};

function lifecycleFromStatus(
  status: JobState["status"] | undefined,
): AnalyzeTitleLifecycle {
  if (status === "extracting") return "extracting";
  if (status === "done") return "partial analysis";
  if (status === "partial") return "partial analysis";
  if (status === "failed") return "failed analysis";
  return "analyzing";
}

export function analyzedTitleSource(opts: {
  pageTitle?: string | null;
  url?: string | null;
}): string {
  const pageTitle = opts.pageTitle?.trim();
  if (pageTitle) return pageTitle;
  const url = opts.url?.trim();
  if (url) return url;
  return DEFAULT_ANALYZED_TITLE;
}

export function truncateAnalyzeTitleSegment(
  value: string,
  max = DEFAULT_TITLE_SEGMENT_MAX,
): string {
  const trimmed = value.trim();
  if (trimmed.length <= max) return trimmed;
  if (max <= 3) return trimmed.slice(0, max);
  return `${trimmed.slice(0, max - 3).trimEnd()}...`;
}

export function lifecycleLabelForJob(
  job: JobState | null,
): AnalyzeTitleLifecycle {
  if (job === null) return "analyzing";
  const activityLabel = job.activity_label?.trim();
  if (activityLabel) {
    return ACTIVITY_LIFECYCLES[activityLabel] ?? "analyzing";
  }
  return lifecycleFromStatus(job.status);
}

export function formatAnalyzeDocumentTitle(input: {
  job: JobState | null;
  overallDecision: OverallDecision | null;
  url?: string | null;
}): string {
  const { job, overallDecision } = input;
  if (job === null) {
    return [TITLE_PREFIX, "analyzing"].join(TITLE_SEPARATOR);
  }
  if (job.status === "done") {
    const verdict =
      overallDecision === null
        ? "partial analysis"
        : overallDecision.verdict === "pass"
          ? "ok"
          : "flagged";
    const title = truncateAnalyzeTitleSegment(
      analyzedTitleSource({
        pageTitle: job.page_title,
        url: job.url ?? input.url,
      }),
    );
    return [TITLE_PREFIX, verdict, title].join(TITLE_SEPARATOR);
  }
  if (job.status === "partial" || job.status === "failed") {
    const title = truncateAnalyzeTitleSegment(
      analyzedTitleSource({
        pageTitle: job.page_title,
        url: job.url ?? input.url,
      }),
    );
    return [TITLE_PREFIX, lifecycleLabelForJob(job), title].join(
      TITLE_SEPARATOR,
    );
  }
  return [TITLE_PREFIX, lifecycleLabelForJob(job)].join(TITLE_SEPARATOR);
}
