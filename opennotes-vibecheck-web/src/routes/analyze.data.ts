import { action, query, redirect } from "@solidjs/router";
import type { JobState, SectionSlug } from "~/lib/api-client.server";

interface FrameCompatResponse {
  can_iframe: boolean;
  blocking_header: string | null;
}

interface ScreenshotResponse {
  screenshot_url: string;
}

export interface FrameCompatResult {
  canIframe: boolean;
  blockingHeader: string | null;
  screenshotUrl: string | null;
}

export type FrameCompatQueryResult =
  | { ok: true; frameCompat: FrameCompatResult }
  | { ok: false; message: string };

function isHttpUrl(candidate: string): boolean {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export const getFrameCompat = query(
  async (targetUrl: string): Promise<FrameCompatQueryResult> => {
    "use server";
    if (!targetUrl || !isHttpUrl(targetUrl)) {
      return { ok: false, message: "invalid url" };
    }
    const { getClient } = await import("~/lib/api-client.server");
    const client = getClient();
    const frameTask = (async (): Promise<FrameCompatResponse> => {
      try {
        const { data, error } = await client.GET("/api/frame-compat", {
          params: { query: { url: targetUrl } },
        });
        if (error || !data) return { can_iframe: true, blocking_header: null };
        return data as unknown as FrameCompatResponse;
      } catch (err: unknown) {
        console.warn("vibecheck frame-compat probe failed:", err);
        return { can_iframe: true, blocking_header: null };
      }
    })();
    const screenshotTask = (async (): Promise<string | null> => {
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
    })();
    const [frameProbe, screenshotUrl] = await Promise.all([
      frameTask,
      screenshotTask,
    ]);
    return {
      ok: true,
      frameCompat: {
        canIframe: frameProbe.can_iframe,
        blockingHeader: frameProbe.blocking_header,
        screenshotUrl,
      },
    };
  },
  "vibecheck-frame-compat",
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
