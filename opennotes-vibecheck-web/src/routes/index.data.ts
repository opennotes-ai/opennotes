import { query } from "@solidjs/router";
import type { RecentAnalysis } from "~/lib/api-client.server";

export const getRecentAnalyses = query(
  async (): Promise<RecentAnalysis[]> => {
    "use server";
    try {
      const { getClient } = await import("~/lib/api-client.server");
      const client = getClient();
      const { data, error } = await client.GET("/api/analyses/recent");
      if (error || !data) return [];
      return data;
    } catch {
      return [];
    }
  },
  "vibecheck-recent-analyses",
);
