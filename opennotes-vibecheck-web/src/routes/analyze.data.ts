import { action, query, redirect } from "@solidjs/router";
import type { JobState, SectionSlug } from "~/lib/api-client.server";

interface FrameCompatResponse {
  can_iframe: boolean;
  blocking_header: string | null;
  csp_frame_ancestors?: string | null;
  has_archive?: boolean;
}

interface ScreenshotResponse {
  screenshot_url: string;
}

type VibecheckClient = ReturnType<
  typeof import("~/lib/api-client.server").getClient
>;

export interface FrameCompatResult {
  canIframe: boolean;
  blockingHeader: string | null;
  cspFrameAncestors: string | null;
  screenshotUrl: string | null;
  archivedPreviewUrl: string | null;
}

export type FrameCompatQueryResult =
  | { ok: true; frameCompat: FrameCompatResult }
  | { ok: false; message: string };

export type ArchiveProbeResult =
  | {
      ok: true;
      has_archive: boolean;
      archived_preview_url: string | null;
      can_iframe: boolean;
      blocking_header: string | null;
      csp_frame_ancestors: string | null;
    }
  | { ok: false; kind: "transient_error" | "invalid_url" };

function isHttpUrl(candidate: string): boolean {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function isStringOrNullish(value: unknown): value is string | null | undefined {
  return value == null || typeof value === "string";
}

function isFrameCompatResponse(value: unknown): value is FrameCompatResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<FrameCompatResponse>;
  return (
    typeof candidate.can_iframe === "boolean" &&
    typeof candidate.has_archive === "boolean" &&
    isStringOrNullish(candidate.blocking_header) &&
    isStringOrNullish(candidate.csp_frame_ancestors)
  );
}

async function fetchArchiveProbe(
  client: VibecheckClient,
  targetUrl: string,
  jobId?: string,
): Promise<ArchiveProbeResult> {
  try {
    const { data, error } = await client.GET("/api/frame-compat", {
      params: { query: { url: targetUrl } },
    });
    if (error || !data) {
      return { ok: false, kind: "transient_error" };
    }
    if (!isFrameCompatResponse(data)) {
      return { ok: false, kind: "transient_error" };
    }
    const frameProbe = data;
    const hasArchive = Boolean(frameProbe.has_archive);
    const archiveParams = new URLSearchParams({ url: targetUrl });
    if (jobId) archiveParams.set("job_id", jobId);
    return {
      ok: true,
      has_archive: hasArchive,
      archived_preview_url: hasArchive
        ? `/api/archive-preview?${archiveParams.toString()}`
        : null,
      can_iframe: frameProbe.can_iframe,
      blocking_header: frameProbe.blocking_header,
      csp_frame_ancestors: frameProbe.csp_frame_ancestors ?? null,
    };
  } catch (err: unknown) {
    console.warn("vibecheck frame-compat probe failed:", err);
    return { ok: false, kind: "transient_error" };
  }
}

async function fetchScreenshot(
  client: VibecheckClient,
  targetUrl: string,
): Promise<string | null> {
  try {
    const { data, error } = await client.GET("/api/screenshot", {
      params: { query: { url: targetUrl } },
    });
    if (!error && data) {
      return (data as unknown as ScreenshotResponse).screenshot_url ?? null;
    }
    return null;
  } catch (err: unknown) {
    console.warn("vibecheck screenshot fetch failed:", err);
    return null;
  }
}

const getArchiveProbeQuery = query(
  async (targetUrl: string, jobId?: string): Promise<ArchiveProbeResult> => {
    "use server";
    if (!targetUrl || !isHttpUrl(targetUrl)) {
      return { ok: false, kind: "invalid_url" };
    }
    const { getClient } = await import("~/lib/api-client.server");
    const client = getClient();
    return fetchArchiveProbe(client, targetUrl, jobId);
  },
  "vibecheck-archive-probe",
);

export const getArchiveProbe = getArchiveProbeQuery;

const getScreenshotQuery = query(
  async (targetUrl: string): Promise<string | null> => {
    "use server";
    if (!targetUrl || !isHttpUrl(targetUrl)) {
      return null;
    }
    const { getClient } = await import("~/lib/api-client.server");
    const client = getClient();
    return fetchScreenshot(client, targetUrl);
  },
  "vibecheck-screenshot",
);

export const getScreenshot = getScreenshotQuery;

const getFrameCompatQuery = query(
  async (targetUrl: string, jobId?: string): Promise<FrameCompatQueryResult> => {
    "use server";
    if (!targetUrl || !isHttpUrl(targetUrl)) {
      return { ok: false, message: "invalid url" };
    }
    const { getClient } = await import("~/lib/api-client.server");
    const client = getClient();
    const [archiveProbe, screenshotUrl] = await Promise.all([
      fetchArchiveProbe(client, targetUrl, jobId),
      fetchScreenshot(client, targetUrl),
    ]);
    if (!archiveProbe.ok && archiveProbe.kind === "invalid_url") {
      return { ok: false, message: "invalid url" };
    }
    const frameProbe =
      archiveProbe.ok
        ? archiveProbe
        : {
            can_iframe: true,
            blocking_header: null,
            csp_frame_ancestors: null,
            archived_preview_url: null,
          };
    return {
      ok: true,
      frameCompat: {
        canIframe: frameProbe.can_iframe,
        blockingHeader: frameProbe.blocking_header,
        cspFrameAncestors: frameProbe.csp_frame_ancestors,
        screenshotUrl,
        archivedPreviewUrl: frameProbe.archived_preview_url,
      },
    };
  },
  "vibecheck-frame-compat",
);

function abortError(): DOMException {
  return new DOMException("Frame compatibility request aborted", "AbortError");
}

export const getFrameCompat = Object.assign(
  (
    targetUrl: string,
    signalOrJobId?: AbortSignal | string,
    jobId?: string,
  ): Promise<FrameCompatQueryResult> => {
    const signal =
      typeof signalOrJobId === "string" ? undefined : signalOrJobId;
    const archiveJobId =
      typeof signalOrJobId === "string" ? signalOrJobId : jobId;
    if (!signal) return getFrameCompatQuery(targetUrl, archiveJobId);
    if (signal.aborted) return Promise.reject(abortError());

    return new Promise<FrameCompatQueryResult>((resolve, reject) => {
      const onAbort = () => reject(abortError());
      signal.addEventListener("abort", onAbort, { once: true });
      void getFrameCompatQuery(targetUrl, archiveJobId)
        .then(resolve, reject)
        .finally(() => {
          signal.removeEventListener("abort", onAbort);
        });
    });
  },
  getFrameCompatQuery,
);

function redirectParams(params: Record<string, string | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") usp.set(k, v);
  }
  return usp.toString();
}

export async function resolveAnalyzeRedirect(formData: FormData): Promise<never> {
  "use server";
  const { analyzeUrl, VibecheckApiError, clampErrorCode } = await import(
    "~/lib/api-client.server"
  );
  const rawUrl = String(formData.get("url") ?? "").trim();
  if (!rawUrl || !isHttpUrl(rawUrl)) {
    throw redirect("/?error=invalid_url");
  }

  const { getRequestEvent } = await import("solid-js/web");
  const evt = getRequestEvent();
  const { checkAnalyzeRateLimit } = await import("~/lib/rate-limit.server");
  if (!evt?.request?.headers) {
    console.warn(
      JSON.stringify({
        event: "vibecheck.rate_limit.no_request_event",
        route: "resolveAnalyzeRedirect",
      }),
    );
  } else {
    const decision = checkAnalyzeRateLimit(evt.request.headers);
    if (!decision.allowed) {
      console.warn(
        JSON.stringify({
          event: `vibecheck.rate_limit.${decision.outcome}`,
          route: "resolveAnalyzeRedirect",
          ip_hash_prefix: decision.ipHashPrefix,
          retry_after_sec: decision.retryAfterSec,
          xff_entry_count: (evt.request.headers.get("x-forwarded-for") ?? "")
            .split(",")
            .filter((p) => p.trim() !== "").length,
        }),
      );
      const qs = redirectParams({
        pending_error: "rate_limited",
        url: rawUrl,
      });
      throw redirect(`/analyze?${qs}`);
    }
  }

  let response;
  try {
    response = await analyzeUrl(rawUrl);
  } catch (err: unknown) {
    if (err instanceof VibecheckApiError) {
      const code = clampErrorCode(err.errorBody?.error_code);
      const host = err.errorBody?.error_host;
      if (code === "invalid_url") {
        throw redirect("/?error=invalid_url");
      }
      if (code === "unsupported_site") {
        const qs = redirectParams({
          pending_error: "unsupported_site",
          url: rawUrl,
          host,
        });
        throw redirect(`/analyze?${qs}`);
      }
      const qs = redirectParams({
        pending_error: code ?? "upstream_error",
        url: rawUrl,
      });
      throw redirect(`/analyze?${qs}`);
    }
    throw err;
  }

  const qs = new URLSearchParams({ job: response.job_id });
  if (response.cached) qs.set("c", "1");
  throw redirect(`/analyze?${qs.toString()}`);
}

export const analyzeAction = action(async (formData: FormData) => {
  "use server";
  await resolveAnalyzeRedirect(formData);
}, "vibecheck-analyze");

export async function pollJobState(jobId: string): Promise<JobState> {
  "use server";
  const { pollJob } = await import("~/lib/api-client.server");
  return pollJob(jobId);
}

export const retrySectionAction = action(
  async (formData: FormData) => {
    "use server";
    const { retrySection } = await import("~/lib/api-client.server");
    const jobId = String(formData.get("job_id") ?? "");
    const slug = String(formData.get("slug") ?? "") as SectionSlug;
    if (!jobId || !slug) {
      throw new Error("retrySectionAction: job_id and slug are required");
    }
    return retrySection(jobId, slug);
  },
  "vibecheck-retry-section",
);
