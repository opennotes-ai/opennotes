import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import type { RecentAnalysis } from "../../src/lib/api-client.server";
import RecentlyVibeChecked from "../../src/components/RecentlyVibeChecked";

afterEach(() => {
  cleanup();
});

function makeAnalysis(overrides?: Partial<RecentAnalysis>): RecentAnalysis {
  return {
    job_id: "job-1",
    source_url: "https://example.com/article",
    page_title: "Example Article",
    screenshot_url: "https://cdn.example.com/shot.png",
    preview_description: "A short preview.",
    completed_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("<RecentlyVibeChecked />", () => {
  it("renders N cards from fixture data", () => {
    const analyses = [
      makeAnalysis({ job_id: "job-1", page_title: "Article One" }),
      makeAnalysis({ job_id: "job-2", page_title: "Article Two" }),
      makeAnalysis({ job_id: "job-3", page_title: "Article Three" }),
    ];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(3);
  });

  it("card href is /analyze?job=<job_id> (NOT ?url=)", () => {
    const analyses = [
      makeAnalysis({ job_id: "abc-123", page_title: "My Article" }),
    ];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    const link = screen.getByRole("link") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/analyze?job=abc-123");
    expect(link.getAttribute("href")).not.toContain("url=");
  });

  it("empty data hides section (no header, no cards rendered)", () => {
    render(() => <RecentlyVibeChecked analyses={[]} />);

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("fixture with missing page_title (null) renders without crashing", () => {
    const analyses = [makeAnalysis({ page_title: null })];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
  });

  it("fixture with empty string preview_description renders without crashing", () => {
    const analyses = [makeAnalysis({ preview_description: "" })];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
  });
});
