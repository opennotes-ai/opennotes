import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@solidjs/testing-library";

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
    completed_at: "2026-05-08T00:00:00Z",
  },
];

describe("<RecentlyVibeChecked />", () => {
  it("tile wrapper has pb-8 and pr-8 padding so FeedbackBell clears content", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={mockAnalyses} />
    ));

    const wrapper = container.querySelector('[data-testid="recently-vibe-checked"] .relative');
    expect(wrapper).not.toBeNull();
    expect(wrapper!.className).toContain("pb-8");
    expect(wrapper!.className).toContain("pr-8");
  });
});
