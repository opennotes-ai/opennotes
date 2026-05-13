import { vi, describe, it, expect, afterEach } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import { createEffect, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import {
  HighlightsStoreProvider,
  useHighlights,
} from "~/components/highlights/HighlightsStoreProvider";
import type { HighlightItem } from "~/components/highlights/highlights-store";
import HeadlineLeadIn from "./HeadlineLeadIn";

vi.mock("embla-carousel-autoplay", () => ({
  default: vi.fn(() => ({ name: "autoplay", isPlaying: () => false, play: vi.fn(), timeUntilNext: () => null })),
}));

vi.mock("embla-carousel-ssr", () => ({
  default: vi.fn(() => ({ name: "ssr" })),
}));

vi.mock("@opennotes/ui/components/ui/carousel", () => {
  const { createContext, useContext } = require("solid-js") as typeof import("solid-js");
  const Ctx = createContext({ scrollPrev: () => {}, scrollNext: () => {}, canScrollPrev: () => true, canScrollNext: () => true });
  function Carousel(props: { children: JSX.Element; opts?: unknown; plugins?: unknown; setApi?: unknown }) {
    return <div data-testid="carousel">{props.children}</div>;
  }
  function CarouselContent(props: { children: JSX.Element }) {
    return <div>{props.children}</div>;
  }
  function CarouselItem(props: { children: JSX.Element }) {
    return <div>{props.children}</div>;
  }
  function CarouselPrevious(props: { "data-testid"?: string; class?: string }) {
    const ctx = useContext(Ctx);
    return <button data-testid={props["data-testid"]} onClick={() => ctx.scrollPrev()} aria-label="Previous slide">Prev</button>;
  }
  function CarouselNext(props: { "data-testid"?: string; class?: string }) {
    const ctx = useContext(Ctx);
    return <button data-testid={props["data-testid"]} onClick={() => ctx.scrollNext()} aria-label="Next slide">Next</button>;
  }
  return { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext };
});

vi.mock("@opennotes/ui/components/ui/progress-circle", () => ({
  ProgressCircle: (props: { value?: number; "data-testid"?: string; size?: string; showAnimation?: boolean }) => (
    <div data-testid={props["data-testid"]} data-value={String(props.value ?? 0)} aria-label="progress" />
  ),
}));

type WeatherReportData = components["schemas"]["WeatherReport"];

function makeHeadline(): ResolvedHeadline {
  return {
    text: "A concise lead-in summary.",
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

function makeItem(id: string, title: string): HighlightItem {
  return { id, source: "test", title };
}

function WithHighlights(props: { items: HighlightItem[]; children: JSX.Element }): JSX.Element {
  const store = useHighlights();
  createEffect(() => {
    if (props.items.length > 0) store.push("test", props.items);
  });
  return <>{props.children}</>;
}

function renderWithHighlights(
  items: HighlightItem[],
  headline: ResolvedHeadline | null,
  weatherReport: WeatherReportData | null,
) {
  return render(() => (
    <HighlightsStoreProvider>
      <WithHighlights items={items}>
        <HeadlineLeadIn headline={headline} weatherReport={weatherReport} />
      </WithHighlights>
    </HighlightsStoreProvider>
  ));
}

afterEach(() => {
  cleanup();
});

describe("HeadlineLeadIn highlights slot (TASK-1631.01)", () => {
  it("renders highlights-card inside the right column when store has items and weather is present", () => {
    renderWithHighlights(
      [makeItem("h1", "Key point")],
      makeHeadline(),
      makeWeatherReport(),
    );
    const chrome = screen.getByTestId("headline-summary-chrome");
    const card = screen.getByTestId("highlights-card");
    expect(chrome).toBeDefined();
    expect(card).toBeDefined();
    expect(
      chrome.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("renders highlights-card when no weather present (single-column layout)", () => {
    renderWithHighlights(
      [makeItem("h1", "Key point")],
      makeHeadline(),
      null,
    );
    expect(screen.getByTestId("highlights-card")).toBeDefined();
  });

  it("does not render highlights-card when store is empty", () => {
    renderWithHighlights([], makeHeadline(), makeWeatherReport());
    expect(screen.queryByTestId("highlights-card")).toBeNull();
  });

  it("does not render highlights-card when no HighlightsStoreProvider in context", () => {
    render(() => (
      <HeadlineLeadIn headline={makeHeadline()} weatherReport={makeWeatherReport()} />
    ));
    expect(screen.queryByTestId("highlights-card")).toBeNull();
  });

  it("right-column wrapper contains headline-summary-chrome before highlights-card", () => {
    renderWithHighlights(
      [makeItem("h1", "Key point"), makeItem("h2", "Another point")],
      makeHeadline(),
      makeWeatherReport(),
    );
    const chrome = screen.getByTestId("headline-summary-chrome");
    const card = screen.getByTestId("highlights-card");
    const wrapper = chrome.parentElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper).toBe(card.parentElement);
    const children = Array.from(wrapper!.children);
    expect(children.indexOf(chrome)).toBeLessThan(children.indexOf(card));
  });
});
