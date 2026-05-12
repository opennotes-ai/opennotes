import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import { HighlightsStoreProvider, useHighlights } from "./HighlightsStoreProvider";
import { HighlightsCard, HIGHLIGHTS_AUTOPLAY_MS } from "./HighlightsCard";
import type { HighlightItem } from "./highlights-store";
import type { JSX } from "solid-js";

const { mockAutoplayPlay, mockAutoplayPlugin } = vi.hoisted(() => {
  const mockAutoplayPlay = vi.fn();
  const mockAutoplayPlugin = {
    name: "autoplay",
    isPlaying: () => false,
    play: mockAutoplayPlay,
    timeUntilNext: () => null,
  };
  return { mockAutoplayPlay, mockAutoplayPlugin };
});

vi.mock("embla-carousel-autoplay", () => ({
  default: vi.fn(() => mockAutoplayPlugin),
}));

vi.mock("embla-carousel-ssr", () => ({
  default: vi.fn(() => ({ name: "ssr" })),
}));

vi.mock("@opennotes/ui/components/ui/carousel", () => {
  const { createContext, useContext } = require("solid-js") as typeof import("solid-js");

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

function makeItem(id: string, title: string): HighlightItem {
  return { id, source: "test", title };
}

function PopulateAndRender(props: { items: HighlightItem[] }): JSX.Element {
  const store = useHighlights();
  if (props.items.length > 0) {
    store.push("test", props.items);
  }
  return <HighlightsCard />;
}

function renderWithItems(items: HighlightItem[]) {
  return render(() => (
    <HighlightsStoreProvider>
      <PopulateAndRender items={items} />
    </HighlightsStoreProvider>
  ));
}

describe("HighlightsCard", () => {
  afterEach(cleanup);

  describe("empty store", () => {
    it("renders null when no items", () => {
      renderWithItems([]);
      expect(screen.queryByTestId("highlights-card")).toBeNull();
    });
  });

  describe("two highlights", () => {
    const twoItems = [makeItem("1", "First highlight"), makeItem("2", "Second highlight")];

    it("renders both slide titles in the DOM", () => {
      renderWithItems(twoItems);
      expect(screen.getByText("First highlight")).toBeTruthy();
      expect(screen.getByText("Second highlight")).toBeTruthy();
    });

    it("renders prev and next buttons", () => {
      renderWithItems(twoItems);
      expect(screen.getByTestId("highlights-prev")).toBeTruthy();
      expect(screen.getByTestId("highlights-next")).toBeTruthy();
    });

    it("renders the progress circle", () => {
      renderWithItems(twoItems);
      expect(screen.getByTestId("highlights-progress")).toBeTruthy();
    });

    it("renders two slides", () => {
      renderWithItems(twoItems);
      const slides = screen.getAllByTestId("highlight-slide");
      expect(slides).toHaveLength(2);
    });
  });

  describe("single highlight", () => {
    const oneItem = [makeItem("1", "Only one")];

    it("renders the single item title", () => {
      renderWithItems(oneItem);
      expect(screen.getByText("Only one")).toBeTruthy();
    });

    it("does not render nav buttons when only one item", () => {
      renderWithItems(oneItem);
      expect(screen.queryByTestId("highlights-prev")).toBeNull();
      expect(screen.queryByTestId("highlights-next")).toBeNull();
    });

    it("does not render progress circle when only one item", () => {
      renderWithItems(oneItem);
      expect(screen.queryByTestId("highlights-progress")).toBeNull();
    });
  });

  describe("HIGHLIGHTS_AUTOPLAY_MS constant", () => {
    it("is exported and equals 5000", () => {
      expect(HIGHLIGHTS_AUTOPLAY_MS).toBe(5000);
    });
  });

  describe("progress circle", () => {
    it("starts at 0 when api is undefined (no embla instance)", () => {
      renderWithItems([makeItem("1", "A"), makeItem("2", "B")]);
      const ring = screen.getByTestId("highlights-progress");
      expect(ring.getAttribute("data-value")).toBe("0");
    });
  });

  describe("autoplay start", () => {
    it("calls play() on the autoplay plugin when the carousel api becomes available", () => {
      mockAutoplayPlay.mockClear();
      renderWithItems([makeItem("1", "A"), makeItem("2", "B")]);
      expect(mockAutoplayPlay).toHaveBeenCalledOnce();
    });
  });
});
