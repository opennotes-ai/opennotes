import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { InternalRecentAnalysis } from "~/lib/api-client.server";

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

const analyses: InternalRecentAnalysis[] = [
  {
    job_id: "job-1",
    source_type: "url",
    source_url: "http://localhost/private",
    page_title: "Private Page",
    screenshot_url: "https://example.com/screenshot.png",
    preview_description: "Private preview",
    headline_summary: null,
    weather_report: null,
    safety_recommendation: null,
    completed_at: "2026-05-12T00:00:00Z",
  },
  {
    job_id: "job-pdf",
    source_type: "pdf",
    source_url: "https://example.com/report.pdf",
    page_title: "Quarterly Report",
    screenshot_url: null,
    preview_description: null,
    headline_summary: null,
    weather_report: null,
    safety_recommendation: null,
    completed_at: "2026-05-12T00:00:01Z",
  },
  {
    job_id: "job-html",
    source_type: "browser_html",
    source_url: "https://example.com/captured",
    page_title: null,
    screenshot_url: null,
    preview_description: null,
    headline_summary: null,
    weather_report: null,
    safety_recommendation: null,
    completed_at: "2026-05-12T00:00:02Z",
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
    const cards = screen.getAllByTestId("internal-gallery-card");
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveAttribute("href", "/analyze?job=job-1");
    expect(cards[1]).toHaveAttribute("href", "/analyze?job=job-pdf");
    expect(cards[2]).toHaveAttribute("href", "/analyze?job=job-html");
    expect(screen.queryByText(/filter/i)).toBeNull();
  });

  it("renders pdf and browser_html cards with null screenshot/preview", async () => {
    const { InternalGalleryGrid } = await import("./gallery");

    render(() => <InternalGalleryGrid analyses={analyses} />);

    expect(screen.getByText("Quarterly Report")).toBeInTheDocument();
    expect(screen.getAllByText("https://example.com/captured").length).toBeGreaterThan(0);
    expect(screen.getByText("pdf")).toBeInTheDocument();
    expect(screen.getByText("browser_html")).toBeInTheDocument();
  });
});
