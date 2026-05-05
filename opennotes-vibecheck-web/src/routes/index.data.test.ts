import { describe, expect, it, vi, beforeEach } from "vitest";

const { clientGetMock } = vi.hoisted(() => ({
  clientGetMock: vi.fn(),
}));

vi.mock("~/lib/api-client.server", async () => {
  const actual = await vi.importActual<typeof import("~/lib/api-client.server")>(
    "~/lib/api-client.server",
  );
  return { ...actual, getClient: () => ({ GET: clientGetMock }) };
});

describe("getRecentAnalyses", () => {
  beforeEach(() => {
    clientGetMock.mockReset();
    vi.resetModules();
  });

  it("returns typed RecentAnalysis[] on success", async () => {
    const fixture = [
      {
        job_id: "job-1",
        source_url: "https://example.com/article",
        page_title: "Example Article",
        screenshot_url: "https://cdn.example.com/shot.png",
        preview_description: "A short preview.",
        completed_at: "2026-01-01T00:00:00Z",
      },
    ];
    clientGetMock.mockResolvedValueOnce({ data: fixture, error: null });

    const { getRecentAnalyses } = await import("./index.data");
    const result = await getRecentAnalyses();

    expect(result).toEqual(fixture);
    expect(clientGetMock).toHaveBeenCalledWith("/api/analyses/recent");
  });

  it("returns [] when API returns error", async () => {
    clientGetMock.mockResolvedValueOnce({ data: null, error: "server error" });

    const { getRecentAnalyses } = await import("./index.data");
    const result = await getRecentAnalyses();

    expect(result).toEqual([]);
  });

  it("returns [] when client.GET throws (network error)", async () => {
    clientGetMock.mockRejectedValueOnce(new Error("network error"));

    const { getRecentAnalyses } = await import("./index.data");
    const result = await getRecentAnalyses();

    expect(result).toEqual([]);
  });
});
