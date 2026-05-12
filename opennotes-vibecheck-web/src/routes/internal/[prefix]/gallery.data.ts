import { query } from "@solidjs/router";
import type { RecentAnalysis } from "~/lib/api-client.server";

function normalizeLimit(limit: number): number {
  if (!Number.isFinite(limit)) return 25;
  return Math.trunc(limit);
}

function isNotFoundError(error: unknown): boolean {
  if (error instanceof Response) return error.status === 404;
  if (typeof error !== "object" || error === null) return false;
  const candidate = error as { status?: unknown; statusCode?: unknown };
  return candidate.status === 404 || candidate.statusCode === 404;
}

function throwNotFound(): never {
  throw new Response(null, { status: 404 });
}

export const getInternalRecentAnalyses = query(
  async (prefix: string, limit: number): Promise<RecentAnalysis[]> => {
    "use server";
    try {
      const { getClient } = await import("~/lib/api-client.server");
      const client = getClient();
      const { data, error, response } = await client.GET(
        "/api/internal/analyses/recent-unfiltered",
        {
          params: { query: { limit: normalizeLimit(limit) } },
          headers: { "X-Internal-Prefix": prefix },
        },
      );
      if (response?.status === 404) throwNotFound();
      if (error || !data) return [];
      return data;
    } catch (error) {
      if (isNotFoundError(error)) throwNotFound();
      return [];
    }
  },
  "vibecheck-internal-recent-analyses",
);
