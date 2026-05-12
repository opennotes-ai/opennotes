import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "./carousel";

vi.mock("embla-carousel-solid", () => ({
  default: vi.fn(() => {
    const listeners: Record<string, Array<(...args: unknown[]) => void>> = {};
    const api = {
      canGoToPrev: vi.fn(() => false),
      canGoToNext: vi.fn(() => true),
      goToPrev: vi.fn(),
      goToNext: vi.fn(),
      on: vi.fn((event: string, cb: (...args: unknown[]) => void) => {
        listeners[event] = listeners[event] ?? [];
        listeners[event].push(cb);
        return api;
      }),
      off: vi.fn(() => api),
    };
    const ref = vi.fn();
    return [ref, () => api, api];
  }),
}));

afterEach(() => {
  cleanup();
});

describe("<Carousel />", () => {
  it("renders children inside a region with aria-roledescription=carousel", () => {
    render(() => (
      <Carousel>
        <CarouselContent>
          <CarouselItem>Slide A</CarouselItem>
          <CarouselItem>Slide B</CarouselItem>
        </CarouselContent>
      </Carousel>
    ));

    const region = screen.getByRole("region");
    expect(region).toBeTruthy();
    expect(region.getAttribute("aria-roledescription")).toBe("carousel");
  });

  it("renders all slides in the DOM", () => {
    render(() => (
      <Carousel>
        <CarouselContent>
          <CarouselItem>Slide A</CarouselItem>
          <CarouselItem>Slide B</CarouselItem>
        </CarouselContent>
      </Carousel>
    ));

    expect(screen.getByText("Slide A")).toBeTruthy();
    expect(screen.getByText("Slide B")).toBeTruthy();
  });

  it("each CarouselItem has role=group and aria-roledescription=slide", () => {
    render(() => (
      <Carousel>
        <CarouselContent>
          <CarouselItem>Slide A</CarouselItem>
          <CarouselItem>Slide B</CarouselItem>
        </CarouselContent>
      </Carousel>
    ));

    const slides = screen.getAllByRole("group");
    expect(slides.length).toBe(2);
    for (const slide of slides) {
      expect(slide.getAttribute("aria-roledescription")).toBe("slide");
    }
  });

  it("renders CarouselPrevious and CarouselNext as buttons", () => {
    render(() => (
      <Carousel>
        <CarouselContent>
          <CarouselItem>Slide A</CarouselItem>
        </CarouselContent>
        <CarouselPrevious />
        <CarouselNext />
      </Carousel>
    ));

    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    const srTexts = buttons.map((b) => b.querySelector(".sr-only")?.textContent);
    expect(srTexts).toContain("Previous slide");
    expect(srTexts).toContain("Next slide");
  });

  it("CarouselPrevious is disabled when canGoToPrev returns false", () => {
    render(() => (
      <Carousel>
        <CarouselContent>
          <CarouselItem>Slide A</CarouselItem>
        </CarouselContent>
        <CarouselPrevious />
        <CarouselNext />
      </Carousel>
    ));

    const buttons = screen.getAllByRole("button");
    const prevBtn = buttons.find(
      (b) => b.querySelector(".sr-only")?.textContent === "Previous slide",
    );
    expect(prevBtn).toBeTruthy();
    expect((prevBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("supports horizontal and vertical orientations without throwing", () => {
    expect(() => {
      render(() => (
        <Carousel orientation="vertical">
          <CarouselContent>
            <CarouselItem>Slide A</CarouselItem>
          </CarouselContent>
        </Carousel>
      ));
    }).not.toThrow();
    cleanup();
    expect(() => {
      render(() => (
        <Carousel orientation="horizontal">
          <CarouselContent>
            <CarouselItem>Slide A</CarouselItem>
          </CarouselContent>
        </Carousel>
      ));
    }).not.toThrow();
  });
});
