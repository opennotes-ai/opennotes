import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { AudienceCard, type AudienceCardProps } from "./audience-card";

const cardSource = readFileSync(
  resolve("src/components/audience-card.tsx"),
  "utf8",
);

describe("<AudienceCard /> source contract", () => {
  it("composes the existing Card primitive", () => {
    expect(cardSource).toContain('from "./ui/card"');
    expect(cardSource).toContain("<Card");
    expect(cardSource).toContain("<CardHeader");
    expect(cardSource).toContain("<CardTitle");
    expect(cardSource).toContain("<CardContent");
    expect(cardSource).toContain("<CardFooter");
  });

  it("wraps the card in a same-tab anchor (no target=_blank)", () => {
    expect(cardSource).toContain("<a");
    expect(cardSource).toContain("href={local.href}");
    expect(cardSource).not.toContain('target="_blank"');
  });

  it("defaults link label to 'Learn more'", () => {
    expect(cardSource).toContain('local.linkLabel ?? "Learn more"');
  });

  it("renders an arrow indicator with aria-hidden", () => {
    expect(cardSource).toContain('aria-hidden="true"');
    expect(cardSource).toContain("→");
  });

  it("uses token color classes only (no inline hex)", () => {
    expect(cardSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(cardSource).toContain("text-muted-foreground");
    expect(cardSource).toContain("text-foreground");
  });

  it("does not use border-stripes or large icon-above-heading", () => {
    expect(cardSource).not.toMatch(/border-l-\[/);
    expect(cardSource).not.toMatch(/border-r-\[/);
  });

  it("provides focus-visible ring styling on the anchor", () => {
    expect(cardSource).toContain("focus-visible:ring");
  });

  it("renders eyebrow icon conditionally via Show", () => {
    expect(cardSource).toContain("Show when={local.icon}");
  });
});

describe("<AudienceCard /> module surface", () => {
  it("exports AudienceCard as a function", () => {
    expect(typeof AudienceCard).toBe("function");
  });

  it("accepts eyebrow, title, body, href props", () => {
    const props: AudienceCardProps = {
      eyebrow: "E",
      title: "T",
      body: "B",
      href: "/x",
    };
    expect(props.eyebrow).toBe("E");
    expect(props.href).toBe("/x");
  });

  it("accepts optional icon and linkLabel", () => {
    const props: AudienceCardProps = {
      eyebrow: "E",
      title: "T",
      body: "B",
      href: "/x",
      linkLabel: "Read",
      icon: null,
    };
    expect(props.linkLabel).toBe("Read");
    expect(props.icon).toBeNull();
  });
});
