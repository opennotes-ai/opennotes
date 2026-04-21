import { action, query, redirect } from "@solidjs/router";
import type { SidebarPayload } from "~/lib/api-client.server";

export type AnalyzeQueryResult =
  | { ok: true; payload: SidebarPayload }
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
      const { analyzeUrl } = await import("~/lib/api-client.server");
      const payload = await analyzeUrl(targetUrl);
      return { ok: true, payload };
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
