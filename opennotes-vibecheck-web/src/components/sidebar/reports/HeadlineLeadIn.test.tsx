import { createSignal } from "solid-js";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import HeadlineLeadIn from "./HeadlineLeadIn";

type WeatherReportData = components["schemas"]["WeatherReport"];

function makeHeadline(): ResolvedHeadline {
  return {
    text: "A concise lead-in summary about the conversation.",
    kind: "synthesized",
    source: "server",
    unavailable_inputs: [],
  } as ResolvedHeadline;
}

function makeWeatherReport(): WeatherReportData {
  return {
    truth: { label: "first_person", logprob: null, alternatives: [] },
    relevance: { label: "on_topic", logprob: null, alternatives: [] },
    sentiment: { label: "neutral", logprob: null, alternatives: [] },
  };
}

afterEach(() => {
  cleanup();
});

describe("HeadlineLeadIn headline skeleton", () => {
  it("renders the headline-summary-skeleton testid when only showHeadlineSkeleton is set", () => {
    render(() => (
      <HeadlineLeadIn
        headline={null}
        weatherReport={null}
        showHeadlineSkeleton
      />
    ));
    expect(screen.getByTestId("headline-summary-skeleton")).toBeDefined();
  });

  it("renders 2-3 narrow text-line-height skeleton bars (h-4 or h-5), not oversized blocks", () => {
    render(() => (
      <HeadlineLeadIn
        headline={null}
        weatherReport={null}
        showHeadlineSkeleton
      />
    ));
    const skeleton = screen.getByTestId("headline-summary-skeleton");
    const bars = skeleton.querySelectorAll("[data-opennotes-skeleton]");
    expect(bars.length).toBeGreaterThanOrEqual(2);
    expect(bars.length).toBeLessThanOrEqual(3);
    bars.forEach((bar) => {
      const cls = bar.getAttribute("class") ?? "";
      expect(cls).toMatch(/\bh-(4|5)\b/);
      expect(cls).not.toMatch(/\bh-(8|10|12|16|20|24|32)\b/);
    });
  });

  it("does not use legacy skeleton-pulse-extra classes inside the headline skeleton", () => {
    render(() => (
      <HeadlineLeadIn
        headline={null}
        weatherReport={null}
        showHeadlineSkeleton
      />
    ));
    const skeleton = screen.getByTestId("headline-summary-skeleton");
    expect(skeleton.querySelector(".skeleton-pulse-extra")).toBeNull();
    expect(
      skeleton.querySelector(".skeleton-pulse-extra-delay-1"),
    ).toBeNull();
    expect(
      skeleton.querySelector(".skeleton-pulse-extra-delay-2"),
    ).toBeNull();
  });

  it("replaces the headline skeleton with the real headline-summary when data arrives", async () => {
    const [headline, setHeadline] = createSignal<ResolvedHeadline | null>(null);
    render(() => (
      <HeadlineLeadIn
        headline={headline()}
        weatherReport={null}
        showHeadlineSkeleton
      />
    ));

    expect(screen.getByTestId("headline-summary-skeleton")).toBeDefined();
    expect(screen.queryByTestId("headline-summary")).toBeNull();

    setHeadline(makeHeadline());

    await waitFor(() => {
      expect(screen.queryByTestId("headline-summary-skeleton")).toBeNull();
      expect(screen.getByTestId("headline-summary")).toBeDefined();
    });
  });

  it("wraps the real headline in card chrome (bg-card)", () => {
    render(() => (
      <HeadlineLeadIn headline={makeHeadline()} weatherReport={null} />
    ));
    const summary = screen.getByTestId("headline-summary");
    const chrome = summary.closest('[data-testid="headline-summary-chrome"]');
    expect(chrome).not.toBeNull();
    const cls = chrome?.getAttribute("class") ?? "";
    expect(cls).toMatch(/\bbg-card\b/);
    expect(cls).toMatch(/\brounded-md\b/);
  });

  it("renders the headline-summary-skeleton inside Card chrome when headline=null and showHeadlineSkeleton=true", () => {
    render(() => (
      <HeadlineLeadIn
        headline={null}
        weatherReport={null}
        showHeadlineSkeleton
      />
    ));
    const skeleton = screen.getByTestId("headline-summary-skeleton");
    const chrome = skeleton.closest('[data-testid="headline-summary-chrome"]');
    expect(chrome).not.toBeNull();
    const cls = chrome?.getAttribute("class") ?? "";
    expect(cls).toMatch(/\bbg-card\b/);
    expect(cls).toMatch(/\brounded-md\b/);
  });

  it("self-defends with skeleton chrome when headline is null but lead-in is visible (weather present)", () => {
    render(() => (
      <HeadlineLeadIn
        headline={null}
        weatherReport={makeWeatherReport()}
      />
    ));
    const skeleton = screen.getByTestId("headline-summary-skeleton");
    const chrome = skeleton.closest('[data-testid="headline-summary-chrome"]');
    expect(chrome).not.toBeNull();
  });
});

describe("HeadlineLeadIn weather-column collapse", () => {
  it("uses auto-fit 2-column layout while weather is loading (skeleton case)", () => {
    render(() => (
      <HeadlineLeadIn
        headline={null}
        weatherReport={null}
        showHeadlineSkeleton
        showWeatherSkeleton
      />
    ));
    const root = screen.getByTestId("headline-lead-in");
    const cls = root.getAttribute("class") ?? "";
    expect(cls).toMatch(/lg:grid-cols-\[max-content_1fr\]/);
    expect(cls).not.toMatch(/1fr\)_minmax\(0,2fr/);
  });

  it("uses auto-fit 2-column layout when both real headline and real weather are present", () => {
    render(() => (
      <HeadlineLeadIn
        headline={makeHeadline()}
        weatherReport={makeWeatherReport()}
      />
    ));
    const root = screen.getByTestId("headline-lead-in");
    const cls = root.getAttribute("class") ?? "";
    expect(cls).toMatch(/lg:grid-cols-\[max-content_1fr\]/);
    expect(cls).not.toMatch(/1fr\)_minmax\(0,2fr/);
  });

  it("collapses to single-column layout when weather is null and not loading (failure case)", () => {
    render(() => (
      <HeadlineLeadIn
        headline={makeHeadline()}
        weatherReport={null}
      />
    ));
    const root = screen.getByTestId("headline-lead-in");
    const cls = root.getAttribute("class") ?? "";
    expect(cls).not.toMatch(/lg:grid-cols-\[max-content_1fr\]/);
    expect(cls).toMatch(/\bgrid-cols-1\b/);
  });

  it("does not render the WeatherReport block when weather is null and not loading", () => {
    render(() => (
      <HeadlineLeadIn headline={makeHeadline()} weatherReport={null} />
    ));
    expect(screen.queryByTestId("weather-report")).toBeNull();
  });

  it("layout class set differs between weather-null+complete and 2-column states", () => {
    const { container: failureContainer } = render(() => (
      <HeadlineLeadIn headline={makeHeadline()} weatherReport={null} />
    ));
    const failureCls =
      failureContainer
        .querySelector('[data-testid="headline-lead-in"]')
        ?.getAttribute("class") ?? "";
    cleanup();

    const { container: twoColContainer } = render(() => (
      <HeadlineLeadIn
        headline={makeHeadline()}
        weatherReport={makeWeatherReport()}
      />
    ));
    const twoColCls =
      twoColContainer
        .querySelector('[data-testid="headline-lead-in"]')
        ?.getAttribute("class") ?? "";

    expect(failureCls).not.toEqual(twoColCls);
    expect(twoColCls).toMatch(/lg:grid-cols-\[max-content_1fr\]/);
    expect(failureCls).not.toMatch(/lg:grid-cols-\[max-content_1fr\]/);
  });

  it("does not pass the vestigial grid-cols-3 lg:grid-cols-1 class to WeatherReport", () => {
    render(() => (
      <HeadlineLeadIn
        headline={makeHeadline()}
        weatherReport={makeWeatherReport()}
      />
    ));
    const weather = screen.getByTestId("weather-report");
    const cls = weather.getAttribute("class") ?? "";
    expect(cls).not.toMatch(/\bgrid-cols-3\b/);
  });
});
