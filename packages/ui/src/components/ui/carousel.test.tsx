import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve("src/components/ui/carousel.tsx"), "utf8");

describe("<Carousel /> recipe — structure and exports", () => {
  it("exports Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext", () => {
    expect(source).toContain("export");
    expect(source).toMatch(/\bCarousel\b/);
    expect(source).toMatch(/\bCarouselContent\b/);
    expect(source).toMatch(/\bCarouselItem\b/);
    expect(source).toMatch(/\bCarouselPrevious\b/);
    expect(source).toMatch(/\bCarouselNext\b/);
  });

  it("imports createEmblaCarousel from embla-carousel-solid", () => {
    expect(source).toContain("embla-carousel-solid");
    expect(source).toContain("createEmblaCarousel");
  });

  it("uses CarouselContext (context-based composition pattern)", () => {
    expect(source).toContain("CarouselContext");
    expect(source).toContain("createContext");
    expect(source).toContain("useContext");
  });

  it("supports horizontal and vertical orientations", () => {
    expect(source).toContain('"horizontal"');
    expect(source).toContain('"vertical"');
  });

  it("supports keyboard navigation (ArrowLeft / ArrowRight)", () => {
    expect(source).toContain("ArrowLeft");
    expect(source).toContain("ArrowRight");
  });

  it("Carousel root has aria role=region and aria-roledescription=carousel", () => {
    expect(source).toContain('role="region"');
    expect(source).toContain('aria-roledescription="carousel"');
  });

  it("CarouselItem has role=group and aria-roledescription=slide", () => {
    expect(source).toMatch(/role="group"/);
    expect(source).toMatch(/aria-roledescription="slide"/);
  });

  it("uses cn() from ../../utils (local package path)", () => {
    expect(source).toContain("../../utils");
    expect(source).toContain("cn(");
  });

  it("imports Button from local button file", () => {
    expect(source).toMatch(/from\s+["']\.\/button["']/);
  });

  it("exports CarouselApi type", () => {
    expect(source).toContain("CarouselApi");
  });

  it("supports optional plugins prop for autoplay etc", () => {
    expect(source).toContain("plugins");
  });

  it("supports setApi prop for external api access", () => {
    expect(source).toContain("setApi");
  });
});
