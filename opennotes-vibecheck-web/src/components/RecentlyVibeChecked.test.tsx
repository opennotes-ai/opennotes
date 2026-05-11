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
  it("does not render a FeedbackBell in gallery items", () => {
    const { container } = render(() => (
      <RecentlyVibeChecked analyses={mockAnalyses} />
    ));

    const bell = container.querySelector('[aria-label*="Send feedback about"]');
    expect(bell).toBeNull();
  });
});
