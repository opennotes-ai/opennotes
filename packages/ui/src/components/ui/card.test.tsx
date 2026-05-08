import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const cardSource = readFileSync(resolve("src/components/ui/card.tsx"), "utf8");

describe("<Card /> CVA variants + polymorphic", () => {
  it("default base classes contain bg-card, text-card-foreground, rounded-md", () => {
    expect(cardSource).toContain("bg-card");
    expect(cardSource).toContain("text-card-foreground");
    expect(cardSource).toContain("rounded-md");
  });

  it("default variant base does NOT contain border or shadow- utilities", () => {
    const cvaCall = cardSource.slice(
      cardSource.indexOf("cva("),
      cardSource.indexOf("defaultVariants"),
    );
    expect(cvaCall).not.toMatch(/\bborder\b/);
    expect(cvaCall).not.toMatch(/shadow-/);
  });

  it("interactive variant contains motion-safe:transition and motion-safe:-translate-y-px", () => {
    expect(cardSource).toContain("motion-safe:transition");
    expect(cardSource).toContain("motion-safe:-translate-y-px");
  });

  it("interactive variant references --card-hover-light and --card-hover-dark-underlit", () => {
    expect(cardSource).toContain("--card-hover-light");
    expect(cardSource).toContain("--card-hover-dark-underlit");
  });

  it("CVA variant prop has default and interactive options", () => {
    expect(cardSource).toContain('"default"');
    expect(cardSource).toContain('"interactive"');
    expect(cardSource).toContain("defaultVariants");
  });

  it("Card uses Dynamic from solid-js/web for polymorphic rendering", () => {
    expect(cardSource).toContain("Dynamic");
    expect(cardSource).toContain("solid-js/web");
  });

  it("polymorphic logic: skips synthetic tabindex when as=a with href", () => {
    expect(cardSource).toContain("tabindex");
    expect(cardSource).toContain("isAnchorWithHref");
  });

  it("sub-components still export and forward class via cn()", () => {
    expect(cardSource).toContain("CardHeader");
    expect(cardSource).toContain("CardTitle");
    expect(cardSource).toContain("CardDescription");
    expect(cardSource).toContain("CardContent");
    expect(cardSource).toContain("CardFooter");
    const cnCount = (cardSource.match(/cn\(/g) ?? []).length;
    expect(cnCount).toBeGreaterThanOrEqual(5);
  });
});
