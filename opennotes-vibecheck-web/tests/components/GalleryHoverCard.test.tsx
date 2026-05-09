import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import type { RecentAnalysis } from "../../src/lib/api-client.server";
import GalleryHoverCard from "../../src/components/GalleryHoverCard";

afterEach(() => {
  cleanup();
});

function makeWeatherReport(): NonNullable<RecentAnalysis["weather_report"]> {
  return {
    truth: { label: "sourced", logprob: null, alternatives: [] },
    relevance: { label: "on_topic", logprob: null, alternatives: [] },
    sentiment: { label: "engaged", logprob: null, alternatives: [] },
  };
}

function makeAnalysis(overrides?: Partial<RecentAnalysis>): RecentAnalysis {
  return {
    job_id: "job-1",
    source_url: "https://example.com/article",
    page_title: "Example Article",
    screenshot_url: "https://cdn.example.com/shot.png",
    preview_description: "A short preview.",
    headline_summary: "Readers are asking for clearer evidence.",
    weather_report: makeWeatherReport(),
    safety_recommendation: null,
    completed_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

async function openHoverCard() {
  await fireEvent.focusIn(screen.getByRole("link", { name: "Example Article" }));
}

describe("<GalleryHoverCard />", () => {
  it("shows weather axes and headline when the trigger receives keyboard focus", async () => {
    render(() => (
      <GalleryHoverCard item={makeAnalysis()} href="/analyze?job=job-1">
        <span>Example Article</span>
      </GalleryHoverCard>
    ));

    await openHoverCard();

    expect(screen.getByTestId("gallery-hover-card")).toBeTruthy();
    expect(screen.getByText("Truth")).toBeTruthy();
    expect(screen.getByText("Sourced")).toBeTruthy();
    expect(screen.getByText("Relevance")).toBeTruthy();
    expect(screen.getByText("On Topic")).toBeTruthy();
    expect(screen.getByText("Sentiment")).toBeTruthy();
    expect(screen.getByText("Engaged")).toBeTruthy();
    expect(screen.getByText("Readers are asking for clearer evidence.")).toBeTruthy();
  });

  it("renders only the child when there is no weather or headline", () => {
    render(() => (
      <GalleryHoverCard
        item={makeAnalysis({ headline_summary: null, weather_report: null })}
        href="/analyze?job=job-1"
      >
        <span>Example Article</span>
      </GalleryHoverCard>
    ));

    expect(screen.getByRole("link", { name: "Example Article" })).toBeTruthy();
    expect(screen.queryByTestId("gallery-hover-card")).toBeNull();
  });

  it("shows safety row with text-color-only class when safety_recommendation is present (caution)", async () => {
    render(() => (
      <GalleryHoverCard
        item={makeAnalysis({
          safety_recommendation: { level: "caution", rationale: "Test rationale" },
        })}
        href="/analyze?job=job-1"
      >
        <span>Example Article</span>
      </GalleryHoverCard>
    ));

    await openHoverCard();

    expect(screen.getByText("Safety")).toBeTruthy();
    const caution = screen.getByText("Caution");
    expect(caution).toBeTruthy();

    const className = caution.className;
    expect(className).toContain("text-amber-700");
    expect(className).not.toContain("bg-");
    expect(className).not.toContain("rounded-");
  });

  it("shows Not available in safety row when safety_recommendation is null", async () => {
    render(() => (
      <GalleryHoverCard
        item={makeAnalysis({ safety_recommendation: null })}
        href="/analyze?job=job-1"
      >
        <span>Example Article</span>
      </GalleryHoverCard>
    ));

    await openHoverCard();

    expect(screen.getByText("Safety")).toBeTruthy();
    expect(screen.getByText("Not available")).toBeTruthy();
  });

  it("other rows use text-color class with no background pill", async () => {
    render(() => (
      <GalleryHoverCard item={makeAnalysis()} href="/analyze?job=job-1">
        <span>Example Article</span>
      </GalleryHoverCard>
    ));

    await openHoverCard();

    const sourced = screen.getByText("Sourced");
    expect(sourced.className).toContain("text-");
    expect(sourced.className).not.toContain("bg-");
    expect(sourced.className).not.toContain("rounded-");

    const onTopic = screen.getByText("On Topic");
    expect(onTopic.className).toContain("text-");
    expect(onTopic.className).not.toContain("bg-");
    expect(onTopic.className).not.toContain("rounded-");

    const engaged = screen.getByText("Engaged");
    expect(engaged.className).toContain("text-");
    expect(engaged.className).not.toContain("bg-");
    expect(engaged.className).not.toContain("rounded-");
  });
});
