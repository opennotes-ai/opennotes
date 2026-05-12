import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { RecentAnalysis } from "~/lib/api-client.server";

const { recentAnalysesMock } = vi.hoisted(() => ({
  recentAnalysesMock: vi.fn(),
}));

vi.mock("./gallery.data", async () => {
  const actual = await vi.importActual<typeof import("./gallery.data")>(
    "./gallery.data",
  );
  return {
    ...actual,
    getInternalRecentAnalyses: recentAnalysesMock,
  };
});

const analyses: RecentAnalysis[] = [
  {
    job_id: "job-1",
    source_url: "http://localhost/private",
    page_title: "Private Page",
    screenshot_url: "https://example.com/screenshot.png",
    preview_description: "Private preview",
    headline_summary: null,
    weather_report: null,
    safety_recommendation: null,
    completed_at: "2026-05-12T00:00:00Z",
  },
];

describe("loadInternalGalleryData", () => {
  const originalPrefix = process.env.VIBECHECK_PRIVATE_PATH_PREFIX;

  beforeEach(() => {
    recentAnalysesMock.mockReset();
    vi.resetModules();
  });

  afterEach(() => {
    if (originalPrefix === undefined) {
      delete process.env.VIBECHECK_PRIVATE_PATH_PREFIX;
    } else {
      process.env.VIBECHECK_PRIVATE_PATH_PREFIX = originalPrefix;
    }
  });

  it("throws 404 before fetching when the env var is empty", async () => {
    delete process.env.VIBECHECK_PRIVATE_PATH_PREFIX;

    const { loadInternalGalleryData } = await import("./gallery");

    await expect(loadInternalGalleryData("anything", "25")).rejects.toMatchObject({
      status: 404,
    });
    expect(recentAnalysesMock).not.toHaveBeenCalled();
  });

  it("throws 404 before fetching when the prefix is wrong", async () => {
    process.env.VIBECHECK_PRIVATE_PATH_PREFIX = "private-prefix";

    const { loadInternalGalleryData } = await import("./gallery");

    await expect(loadInternalGalleryData("wrong", "25")).rejects.toMatchObject({
      status: 404,
    });
    expect(recentAnalysesMock).not.toHaveBeenCalled();
  });

  it("clamps the limit before fetching rows", async () => {
    process.env.VIBECHECK_PRIVATE_PATH_PREFIX = "private-prefix";
    recentAnalysesMock.mockResolvedValueOnce(analyses);

    const { loadInternalGalleryData } = await import("./gallery");
    const result = await loadInternalGalleryData("private-prefix", "500");

    expect(result).toEqual(analyses);
    expect(recentAnalysesMock).toHaveBeenCalledWith("private-prefix", 200);
  });

  it("uses the default limit when no query limit is supplied", async () => {
    process.env.VIBECHECK_PRIVATE_PATH_PREFIX = "private-prefix";
    recentAnalysesMock.mockResolvedValueOnce(analyses);

    const { loadInternalGalleryData } = await import("./gallery");
    await loadInternalGalleryData("private-prefix", undefined);

    expect(recentAnalysesMock).toHaveBeenCalledWith("private-prefix", 25);
  });

  it("clamps low limits to one", async () => {
    process.env.VIBECHECK_PRIVATE_PATH_PREFIX = "private-prefix";
    recentAnalysesMock.mockResolvedValueOnce(analyses);

    const { loadInternalGalleryData } = await import("./gallery");
    await loadInternalGalleryData("private-prefix", "0");

    expect(recentAnalysesMock).toHaveBeenCalledWith("private-prefix", 1);
  });
});

describe("<InternalGalleryGrid />", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders internal gallery cards without public filters", async () => {
    const { InternalGalleryGrid } = await import("./gallery");

    render(() => <InternalGalleryGrid analyses={analyses} />);

    expect(screen.getByText("Internal gallery")).toBeInTheDocument();
    expect(screen.getByTestId("internal-gallery-card")).toHaveAttribute(
      "href",
      "/analyze?job=job-1",
    );
    expect(screen.queryByText(/filter/i)).toBeNull();
  });
});
