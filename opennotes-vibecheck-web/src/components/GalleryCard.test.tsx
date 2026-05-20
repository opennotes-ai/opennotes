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

import GalleryCard from "./GalleryCard";
import type { components } from "~/lib/generated-types";

afterEach(() => {
  cleanup();
});

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type WeatherReport = components["schemas"]["WeatherReport"];

const SAFE_RECOMMENDATION: SafetyRecommendation = {
  level: "safe",
  rationale: "Looks fine",
};

const WEATHER_REPORT: WeatherReport = {
  truth: { label: "sourced", logprob: null, alternatives: [] },
  relevance: { label: "on_topic", logprob: null, alternatives: [] },
  sentiment: { label: "neutral", logprob: null, alternatives: [] },
};

describe("<GalleryCard />", () => {
  it("renders title, snippet, and a background-image url containing the screenshotUrl", () => {
    const { getByText, container } = render(() => (
      <GalleryCard
        href="/analyze?job=abc"
        title="Test Title"
        snippet="Test snippet text"
        screenshotUrl="https://example.com/screenshot.png"
        safetyRecommendation={SAFE_RECOMMENDATION}
        weatherReport={WEATHER_REPORT}
      />
    ));

    expect(getByText("Test Title")).toBeTruthy();
    expect(getByText("Test snippet text")).toBeTruthy();

    const screenshotEl = container.querySelector('[style*="background-image"]');
    expect(screenshotEl).toBeTruthy();
    expect(screenshotEl?.getAttribute("style")).toContain(
      "https://example.com/screenshot.png",
    );
  });

  it("renders WeatherSymbol with level derived from safetyRecommendation", () => {
    const { container } = render(() => (
      <GalleryCard
        href="/analyze?job=abc"
        title="Title"
        snippet={null}
        screenshotUrl="https://example.com/screenshot.png"
        safetyRecommendation={SAFE_RECOMMENDATION}
        weatherReport={WEATHER_REPORT}
      />
    ));

    const symbol = container.querySelector('[data-testid="weather-symbol-safe"]');
    expect(symbol).toBeTruthy();
  });

  it("renders 'unknown' symbol when weatherReport is null", () => {
    const { container } = render(() => (
      <GalleryCard
        href="/analyze?job=abc"
        title="Title"
        snippet={null}
        screenshotUrl="https://example.com/screenshot.png"
        safetyRecommendation={null}
        weatherReport={null}
      />
    ));

    const symbol = container.querySelector('[data-testid="weather-symbol-unknown"]');
    expect(symbol).toBeTruthy();
  });

  it("falls back to screenshotFallback slot when screenshotUrl is null", () => {
    const { getByText } = render(() => (
      <GalleryCard
        href="/analyze?job=abc"
        title="Title"
        snippet={null}
        screenshotUrl={null}
        screenshotFallback={<div>fallback-content</div>}
        safetyRecommendation={null}
        weatherReport={null}
      />
    ));

    expect(getByText("fallback-content")).toBeTruthy();
  });

  it("forwards href to the wrapping anchor", () => {
    const { container } = render(() => (
      <GalleryCard
        href="/analyze?job=target123"
        title="Title"
        snippet={null}
        screenshotUrl={null}
        safetyRecommendation={null}
        weatherReport={null}
      />
    ));

    const anchor = container.querySelector('a[href="/analyze?job=target123"]');
    expect(anchor).toBeTruthy();
  });

  it("forwards data-testid to the outer element", () => {
    const { container } = render(() => (
      <GalleryCard
        href="/analyze?job=abc"
        title="Title"
        snippet={null}
        screenshotUrl={null}
        testid="gallery-card-test"
        safetyRecommendation={null}
        weatherReport={null}
      />
    ));

    const el = container.querySelector('[data-testid="gallery-card-test"]');
    expect(el).toBeTruthy();
  });

  it("does not pass lobe interaction handlers to WeatherSymbol — no data-axis elements have click listeners", () => {
    const { container } = render(() => (
      <GalleryCard
        href="/analyze?job=abc"
        title="Title"
        snippet={null}
        screenshotUrl={null}
        safetyRecommendation={SAFE_RECOMMENDATION}
        weatherReport={WEATHER_REPORT}
      />
    ));

    const lobeEls = container.querySelectorAll("[data-axis]");
    lobeEls.forEach((el) => {
      const htmlEl = el as HTMLElement;
      const hasOnClick = Object.keys(htmlEl).some((k) =>
        k.startsWith("__reactEvents") || k === "onclick",
      );
      expect(hasOnClick).toBe(false);

      const listeners = (htmlEl as unknown as { _listeners?: Record<string, unknown> })._listeners;
      if (listeners) {
        expect(listeners["click"]).toBeUndefined();
      }
    });
  });
});
