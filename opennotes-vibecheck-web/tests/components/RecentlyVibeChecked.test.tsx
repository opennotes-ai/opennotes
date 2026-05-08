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
    headline_summary: null,
    weather_report: null,
    completed_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeWeatherReport(): NonNullable<RecentAnalysis["weather_report"]> {
  return {
    truth: { label: "sourced", logprob: null, alternatives: [] },
    relevance: { label: "on_topic", logprob: null, alternatives: [] },
    sentiment: { label: "engaged", logprob: null, alternatives: [] },
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

  it("feedback bell aria-label uses human-readable ariaContext (page_title) and does not leak job_id or bell_location", () => {
    const analyses = [
      makeAnalysis({
        job_id: "job-aria-1",
        page_title: "How vaccines work",
        source_url: "https://example.com/vaccines",
      }),
    ];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    const bell = screen.getByLabelText(/Send feedback about/i);
    const label = bell.getAttribute("aria-label") ?? "";
    expect(label).toBe("Send feedback about How vaccines work");
    expect(label).not.toContain("job-aria-1");
    expect(label).not.toContain("home:recently-vibe-checked");
  });

  it("feedback bell aria-label falls back to source_url when page_title is null (still no job_id)", () => {
    const analyses = [
      makeAnalysis({
        job_id: "job-aria-2",
        page_title: null,
        source_url: "https://example.com/no-title",
      }),
    ];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    const bell = screen.getByLabelText(/Send feedback about/i);
    const label = bell.getAttribute("aria-label") ?? "";
    expect(label).toBe("Send feedback about https://example.com/no-title");
    expect(label).not.toContain("job-aria-2");
    expect(label).not.toContain("home:recently-vibe-checked");
  });

  it("renders weather readout only for cards with a weather report", () => {
    const analyses = [
      makeAnalysis({
        job_id: "job-with-weather",
        page_title: "Article With Weather",
        weather_report: makeWeatherReport(),
      }),
      makeAnalysis({
        job_id: "job-without-weather",
        page_title: "Article Without Weather",
        weather_report: null,
      }),
    ];

    render(() => <RecentlyVibeChecked analyses={analyses} />);

    expect(screen.getByText("Sourced · On Topic · Engaged")).toBeTruthy();
    expect(screen.getAllByTestId("recent-analysis-weather")).toHaveLength(1);
  });
});
