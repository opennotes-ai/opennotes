import { describe, it, expect, vi, afterEach } from "vitest";
import {
  createContext,
  createEffect,
  createSignal,
  For,
  useContext,
  type JSX,
} from "solid-js";
import { render, screen, cleanup } from "@solidjs/testing-library";
import { HighlightsStoreProvider, useHighlights } from "./HighlightsStoreProvider";
import { SafetyHighlightsBridge } from "./SafetyHighlightsBridge";
import { HighlightsCard } from "./HighlightsCard";
import type { components } from "~/lib/generated-types";

const { mockAutoplayPlugin } = vi.hoisted(() => {
  const mockAutoplayPlugin = {
    name: "autoplay",
    isPlaying: () => false,
    play: vi.fn(),
    timeUntilNext: () => null,
  };
  return { mockAutoplayPlugin };
});

vi.mock("embla-carousel-autoplay", () => ({
  default: vi.fn(() => mockAutoplayPlugin),
}));

vi.mock("embla-carousel-ssr", () => ({
  default: vi.fn(() => ({ name: "ssr" })),
}));

vi.mock("@opennotes/ui/components/ui/carousel", () => {
  const CarouselCtx = createContext<{
    scrollPrev: () => void;
    scrollNext: () => void;
    canScrollPrev: () => boolean;
    canScrollNext: () => boolean;
  }>({
    scrollPrev: () => {},
    scrollNext: () => {},
    canScrollPrev: () => true,
    canScrollNext: () => true,
  });

  const mockScrollNext = vi.fn();
  const mockScrollPrev = vi.fn();

  const mockEmblaInstance = {
    plugins: () => ({ autoplay: mockAutoplayPlugin }),
  };
  const mockApiAccessor = () => mockEmblaInstance;

  function Carousel(props: {
    children?: JSX.Element;
    opts?: unknown;
    plugins?: unknown;
    setApi?: (api: unknown) => void;
  }) {
    props.setApi?.(mockApiAccessor);
    return (
      <div role="region" aria-roledescription="carousel">
        <CarouselCtx.Provider
          value={{
            scrollPrev: mockScrollPrev,
            scrollNext: mockScrollNext,
            canScrollPrev: () => true,
            canScrollNext: () => true,
          }}
        >
          {props.children}
        </CarouselCtx.Provider>
      </div>
    );
  }

  function CarouselContent(props: { children?: JSX.Element }) {
    return <div class="overflow-hidden">{props.children}</div>;
  }

  function CarouselItem(props: { children?: JSX.Element }) {
    return (
      <div role="group" aria-roledescription="slide">
        {props.children}
      </div>
    );
  }

  function CarouselPrevious(props: {
    "data-testid"?: string;
    class?: string;
    disabled?: boolean;
  }) {
    const ctx = useContext(CarouselCtx);
    return (
      <button
        data-testid={props["data-testid"]}
        disabled={!ctx.canScrollPrev()}
        onClick={() => ctx.scrollPrev()}
        aria-label="Previous slide"
      >
        Prev
      </button>
    );
  }

  function CarouselNext(props: {
    "data-testid"?: string;
    class?: string;
    disabled?: boolean;
  }) {
    const ctx = useContext(CarouselCtx);
    return (
      <button
        data-testid={props["data-testid"]}
        disabled={!ctx.canScrollNext()}
        onClick={() => ctx.scrollNext()}
        aria-label="Next slide"
      >
        Next
      </button>
    );
  }

  return { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext };
});

vi.mock("@opennotes/ui/components/ui/progress-circle", () => ({
  ProgressCircle: (props: {
    value?: number;
    "data-testid"?: string;
    size?: string;
    showAnimation?: boolean;
  }) => (
    <div
      data-testid={props["data-testid"]}
      data-value={String(props.value ?? 0)}
      aria-label="progress"
    />
  ),
}));

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type Divergence = components["schemas"]["Divergence"];

function makeDiv(idx: number, overrides: Partial<Divergence> = {}): Divergence {
  return {
    direction: "discounted",
    reason: `Reason ${idx}`,
    signal_source: `source-${idx}`,
    signal_detail: `detail-${idx}`,
    ...overrides,
  };
}

function makeRec(
  divergences: Divergence[],
  overrides: Partial<SafetyRecommendation> = {},
): SafetyRecommendation {
  return {
    ...overrides,
    level: "safe",
    rationale: "rationale",
    divergences,
  };
}

function ProbeItems() {
  const highlights = useHighlights();
  return (
    <div data-testid="probe">
      <For each={highlights.items()}>
        {(it) => (
          <span
            data-testid={`item-${it.id}`}
            data-source={it.source}
            data-severity={it.severity}
            data-detail={it.detail}
          >
            {it.title}
          </span>
        )}
      </For>
    </div>
  );
}

describe("SafetyHighlightsBridge", () => {
  afterEach(cleanup);

  it("populates two divergences in the store", () => {
    const rec = makeRec([
      makeDiv(0),
      makeDiv(1, { direction: "escalated" }),
    ]);
    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(getByTestId("item-safety-divergence:0").textContent).toBe(
      "Discounted: Reason 0",
    );
    expect(getByTestId("item-safety-divergence:1").textContent).toBe(
      "Escalated: Reason 1",
    );
  });

  it("replaces items when recommendation updates to fewer divergences", () => {
    const [rec, setRec] = createSignal<SafetyRecommendation | null>(
      makeRec([makeDiv(0), makeDiv(1)]),
    );

    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec()} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:1")).not.toBeNull();

    setRec(makeRec([makeDiv(0)]));

    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:1")).toBeNull();
  });

  it("clears safety-divergence items when recommendation becomes null", () => {
    const [rec, setRec] = createSignal<SafetyRecommendation | null>(
      makeRec([makeDiv(0)]),
    );

    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec()} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();

    setRec(null);

    expect(queryByTestId("item-safety-divergence:0")).toBeNull();
  });

  it("preserves items from other sources across safety-divergence refreshes", () => {
    const [rec, setRec] = createSignal<SafetyRecommendation | null>(
      makeRec([makeDiv(0)]),
    );

    function SeedOtherSource() {
      const highlights = useHighlights();
      highlights.push("other-source", [
        { id: "other-1", source: "other-source", title: "Other title" },
      ]);
      return null;
    }

    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SeedOtherSource />
        <SafetyHighlightsBridge recommendation={rec()} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(queryByTestId("item-other-1")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();

    setRec(makeRec([makeDiv(0), makeDiv(1)]));

    expect(queryByTestId("item-other-1")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:1")).not.toBeNull();
  });

  it("does not call replaceForSource again when recommendation ref changes but divergences content is identical", () => {
    const [rec, setRec] = createSignal<SafetyRecommendation | null>(
      makeRec([makeDiv(0)]),
    );

    let reactiveReads = 0;

    function RenderCounter() {
      const store = useHighlights();
      createEffect(() => {
        store.items();
        reactiveReads++;
      });
      return null;
    }

    render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec()} />
        <RenderCounter />
      </HighlightsStoreProvider>
    ));

    const countAfterInit = reactiveReads;

    setRec({ ...makeRec([makeDiv(0)]) });

    expect(reactiveReads).toBe(countAfterInit);
  });

  it("maps id, title, detail, and severity correctly", () => {
    const div = makeDiv(0, {
      reason: "Suspicious pattern",
      signal_source: "combined",
      signal_detail: "high confidence match",
      direction: "escalated",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    const el = getByTestId("item-safety-divergence:0");
    expect(el.textContent).toBe("Escalated: Suspicious pattern");
    expect(el.getAttribute("data-source")).toBe("safety-divergence");
    expect(el.getAttribute("data-severity")).toBe("warn");
    expect(el.getAttribute("data-detail")).toBe("Combined signals: high confidence match");
  });

  it.each([
    ["openai", "Text moderation"],
    ["gcp", "Text moderation"],
    ["text", "Text moderation"],
    ["text moderation", "Text moderation"],
    ["text_moderation/gcp", "Text moderation"],
    ["text_moderation/openai", "Text moderation"],
    ["image", "Image moderation"],
    ["image moderation", "Image moderation"],
    ["video", "Video moderation"],
    ["video moderation", "Video moderation"],
    ["web_risk", "Web Risk"],
    ["web risk", "Web Risk"],
    ["combined", "Combined signals"],
    ["combined signals", "Combined signals"],
  ])("maps raw/display source label %s to display label", (signalSource, label) => {
    const div = makeDiv(0, {
      signal_source: signalSource,
      signal_detail: "Contextual evidence",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(getByTestId("item-safety-divergence:0").getAttribute("data-detail")).toBe(
      `${label}: Contextual evidence`,
    );
  });

  it.each([
    ["Discounted: Suspicious legacy pattern", "Discounted: Suspicious legacy pattern"],
    ["EsCaLaTeD suspicious legacy pattern", "Discounted: suspicious legacy pattern"],
    [
      "Escalated: urgent review requested",
      "Escalated: urgent review requested",
    ],
    ["eScAlAtEd suspicious escalated phrase", "Escalated: suspicious escalated phrase"],
  ])("strips duplicated direction prefixes in title %s", (reason, title) => {
    const div = makeDiv(0, {
      direction: title.startsWith("Escalated") ? "escalated" : "discounted",
      reason,
      signal_source: "combined",
      signal_detail: "Contextual evidence",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(getByTestId("item-safety-divergence:0").textContent).toBe(title);
  });

  it.each([
    ["POTENTIALLY_HARMFUL_APPLICATION score 0.72"],
    ["self_harm/intent"],
    ["self-harm/intent"],
    ["harassment_threatening"],
    ["harassment"],
    ["harassment was escalated"],
    ["self-harm was discounted"],
    ["openai moderation flagged context"],
  ])("does not expose raw signal detail %s in highlight details", (signalDetail) => {
    const div = makeDiv(0, {
      reason: "False positive",
      signal_source: "web_risk",
      signal_detail: signalDetail,
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(getByTestId("item-safety-divergence:0").getAttribute("data-detail")).toBe(
      "Web Risk: Signal context adjusted",
    );
  });

  it.each([
    ["self_harm/intent was discounted", "Discounted: Signal context discounted"],
    ["self-harm/intent was discounted", "Discounted: Signal context discounted"],
    [
      "harassment_threatening was escalated",
      "Escalated: Signal context escalated",
    ],
    ["harassment", "Escalated: Signal context escalated"],
    ["harassment was escalated", "Escalated: Signal context escalated"],
    ["self-harm was discounted", "Discounted: Signal context discounted"],
    ["gcp signal discounted", "Discounted: Signal context discounted"],
  ])("does not expose raw signal identifiers in title reason %s", (reason, title) => {
    const div = makeDiv(0, {
      direction: title.startsWith("Escalated") ? "escalated" : "discounted",
      reason,
      signal_source: "combined",
      signal_detail: "Contextual evidence",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(getByTestId("item-safety-divergence:0").textContent).toBe(title);
  });

  it("keeps prose that only contains category text as part of a larger human word", () => {
    const div = makeDiv(0, {
      reason: "Educational sexual-health context",
      signal_source: "text",
      signal_detail: "Educational sexual-health context",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    const item = getByTestId("item-safety-divergence:0");
    expect(item.textContent).toBe("Discounted: Educational sexual-health context");
    expect(item.getAttribute("data-detail")).toBe(
      "Text moderation: Educational sexual-health context",
    );
  });

  it("keeps display-ready slash phrases in divergence text", () => {
    const div = makeDiv(0, {
      reason: "Before/after context changes the interpretation.",
      signal_source: "image moderation",
      signal_detail: "Before/after comparison is educational.",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    const item = getByTestId("item-safety-divergence:0");
    expect(item.textContent).toBe(
      "Discounted: Before/after context changes the interpretation.",
    );
    expect(item.getAttribute("data-detail")).toBe(
      "Image moderation: Before/after comparison is educational.",
    );
  });

  it("hides highlights when no divergences are present", () => {
    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={{ level: "safe", rationale: "No divergences" }} />
        <ProbeItems />
        <HighlightsCard />
      </HighlightsStoreProvider>
    ));

    expect(screen.queryByTestId("highlights-card")).toBeNull();
    expect(queryByTestId("item-safety-divergence:0")).toBeNull();
  });

  it("renders mixed-direction divergences into ordered highlight slides", () => {
    render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge
          recommendation={makeRec([
            makeDiv(0, {
              direction: "discounted",
              reason: "Fact signal",
              signal_source: "text_moderation",
              signal_detail: "Weak signal",
            }),
            makeDiv(1, {
              direction: "escalated",
              reason: "Manual review",
              signal_source: "image_moderation",
              signal_detail: "High confidence",
            }),
          ])}
        />
        <HighlightsCard />
      </HighlightsStoreProvider>
    ));

    const slides = screen.getAllByTestId("highlight-slide");
    expect(slides).toHaveLength(2);
    expect(slides[0]).toHaveTextContent("Discounted: Fact signal");
    expect(slides[0]).toHaveTextContent("Text moderation: Weak signal");
    expect(slides[1]).toHaveTextContent("Escalated: Manual review");
    expect(slides[1]).toHaveTextContent("Image moderation: High confidence");
  });

  it("does not render highlight slides when recommendation divergences are missing", () => {
    render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={{ level: "safe", rationale: "No divergences" }} />
        <HighlightsCard />
      </HighlightsStoreProvider>
    ));

    expect(screen.queryByTestId("highlight-slide")).toBeNull();
  });
});
