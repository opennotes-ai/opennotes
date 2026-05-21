import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@solidjs/testing-library";
import type { JSX } from "solid-js";

vi.mock("./GalleryHoverCard", () => ({
  default: (props: {
    href: string;
    "data-testid"?: string;
    class?: string;
    children: JSX.Element;
  }) => (
    <a href={props.href} data-testid={props["data-testid"]} class={props.class}>
      {props.children}
    </a>
  ),
}));

import RecentlyVibeChecked from "./RecentlyVibeChecked";
import type { RecentAnalysis } from "~/lib/api-client.server";

afterEach(() => {
  cleanup();
});

const mockAnalyses: RecentAnalysis[] = [
  {
    job_id: "abc123",
    source_url: "https://example.com/article",
    page_title: "Test Article",
    preview_description: "A test description",
    screenshot_url: "https://example.com/screenshot.png",
    weather_report: null,
    safety_recommendation: null,
    completed_at: "2026-05-08T00:00:00Z",
  },
  {
    job_id: "def456",
    source_url: "https://example.com/fallback",
    page_title: null,
    preview_description: "Another description",
    screenshot_url: "",
    weather_report: null,
    safety_recommendation: null,
    completed_at: "2026-05-09T00:00:00Z",
  },
];

describe("<RecentlyVibeChecked />", () => {
  it("renders one card per analysis with correct href", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={mockAnalyses} />
    ));

    const cards = container.querySelectorAll('[data-testid="recent-analysis-card"]');
    expect(cards).toHaveLength(2);

    const links = container.querySelectorAll('a[href]');
    const hrefs = Array.from(links).map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("/analyze?job=abc123");
    expect(hrefs).toContain("/analyze?job=def456");
  });

  it("renders page_title when available", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={[mockAnalyses[0]]} />
    ));

    expect(container.textContent).toContain("Test Article");
  });

  it("falls back to source_url when page_title is null", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={[mockAnalyses[1]]} />
    ));

    expect(container.textContent).toContain("https://example.com/fallback");
  });

  it("renders preview_description as snippet", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={[mockAnalyses[0]]} />
    ));

    expect(container.textContent).toContain("A test description");
  });

  it("renders weather symbol via testid", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={[mockAnalyses[0]]} />
    ));

    const symbol = container.querySelector('[data-testid^="weather-symbol-"]');
    expect(symbol).not.toBeNull();
  });

  it("does NOT render the old text weather readout", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={mockAnalyses} />
    ));

    const weatherText = container.querySelector('[data-testid="recent-analysis-weather"]');
    expect(weatherText).toBeNull();
  });

  it("does not render a FeedbackBell in gallery items", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={mockAnalyses} />
    ));

    const bell = container.querySelector('[aria-label*="Send feedback about"]');
    expect(bell).toBeNull();
  });
});
