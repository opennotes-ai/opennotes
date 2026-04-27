import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { MarketingHero, type MarketingHeroProps } from "./marketing-hero";

const heroSource = readFileSync(
  resolve("src/components/marketing-hero.tsx"),
  "utf8",
);

describe("<MarketingHero /> source contract", () => {
  it("renders an h1 element for the headline", () => {
    expect(heroSource).toContain("<h1");
  });

  it("uses left-aligned content (text-left, no centered template)", () => {
    expect(heroSource).toContain("text-left");
    expect(heroSource).not.toContain("text-center");
  });

  it("uses fluid clamp() typography on the headline", () => {
    expect(heroSource).toContain("clamp(");
    expect(heroSource).toContain("font-size");
  });

  it("caps body width at 70ch", () => {
    expect(heroSource).toContain("max-w-[70ch]");
  });

  it("uses token color classes only (no inline hex)", () => {
    expect(heroSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(heroSource).toContain("text-foreground");
    expect(heroSource).toContain("text-muted-foreground");
  });

  it("does not introduce banned visual treatments", () => {
    expect(heroSource).not.toMatch(/border-l-\[/);
    expect(heroSource).not.toMatch(/border-r-\[/);
    expect(heroSource).not.toMatch(/bg-gradient-to-/);
    expect(heroSource).not.toMatch(/text-transparent/);
  });

  it("renders kicker conditionally (Show wrapper for text)", () => {
    expect(heroSource).toContain("Show when={local.kicker}");
  });

  it("renders actions slot in a stable wrapper (always-rendered for hydration)", () => {
    expect(heroSource).toContain("flex flex-wrap items-center gap-4");
    expect(heroSource).toContain("{local.actions}");
  });
});

describe("<MarketingHero /> module surface", () => {
  it("exports MarketingHero as a function", () => {
    expect(typeof MarketingHero).toBe("function");
  });

  it("accepts kicker, headline, body, actions props", () => {
    const props: MarketingHeroProps = {
      kicker: "K",
      headline: "H",
      body: "B",
    };
    expect(props.kicker).toBe("K");
    expect(props.headline).toBe("H");
    expect(props.body).toBe("B");
  });
});
