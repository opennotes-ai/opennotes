import { action, query, redirect } from "@solidjs/router";
import type { SidebarPayload } from "~/lib/api-client.server";

// /api/frame-compat and /api/screenshot responses are plain dicts in the
// backend FastAPI routes (not named pydantic models), so openapi-typescript
// emits them as `{ [key: string]: unknown }` / `{ [key: string]: string }`.
// We narrow at the call site below.
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

export type AnalyzeQueryResult =
  | {
      ok: true;
      payload: SidebarPayload;
      frameCompat: FrameCompatResult;
    }
  | { ok: false; error: "invalid_url" | "upstream_error"; message: string };

function isHttpUrl(candidate: string): boolean {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export const getAnalysis = query(
  async (targetUrl: string): Promise<AnalyzeQueryResult> => {
    "use server";
    if (!targetUrl || !isHttpUrl(targetUrl)) {
      return {
        ok: false,
        error: "invalid_url",
        message: "Provide an http:// or https:// URL to analyze.",
      };
    }
    try {
      const { analyzeUrl, getClient } = await import("~/lib/api-client.server");
      const client = getClient();

      const analysisTask = analyzeUrl(targetUrl);
      const frameTask = (async (): Promise<FrameCompatResponse> => {
        try {
          const { data, error } = await client.GET("/api/frame-compat", {
            params: { query: { url: targetUrl } },
          });
          if (error || !data) {
            return { can_iframe: false, blocking_header: null };
          }
          return data as unknown as FrameCompatResponse;
        } catch (frameError: unknown) {
          console.warn("vibecheck frame-compat probe failed:", frameError);
          return { can_iframe: false, blocking_header: null };
        }
      })();

      const [payload, frameProbe] = await Promise.all([
        analysisTask,
        frameTask,
      ]);

      let screenshotUrl: string | null = null;
      if (!frameProbe.can_iframe) {
        try {
          const { data, error } = await client.GET("/api/screenshot", {
            params: { query: { url: targetUrl } },
          });
          if (!error && data) {
            screenshotUrl =
              (data as unknown as ScreenshotResponse).screenshot_url ?? null;
          }
        } catch (shotError: unknown) {
          console.warn("vibecheck screenshot fetch failed:", shotError);
        }
      }

      return {
        ok: true,
        payload,
        frameCompat: {
          canIframe: frameProbe.can_iframe,
          blockingHeader: frameProbe.blocking_header,
          screenshotUrl,
        },
      };
    } catch (error: unknown) {
      console.error("vibecheck analyze query failed:", error);
      const message =
        error instanceof Error ? error.message : "Analysis failed.";
      return { ok: false, error: "upstream_error", message };
    }
  },
  "vibecheck-analysis",
);

export const analyzeAction = action(async (formData: FormData) => {
  "use server";
  const rawUrl = String(formData.get("url") ?? "").trim();
  if (!rawUrl || !isHttpUrl(rawUrl)) {
    throw redirect("/?error=invalid_url");
  }

  const result = await getAnalysis(rawUrl);
  if (!result.ok) {
    throw redirect(`/?error=${encodeURIComponent(result.error)}`);
  }

  throw redirect(`/analyze?url=${encodeURIComponent(rawUrl)}`);
}, "vibecheck-analyze");
