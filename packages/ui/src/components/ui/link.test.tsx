import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { Link, linkVariants, type LinkProps } from "./link";

const linkSource = readFileSync(
  resolve("src/components/ui/link.tsx"),
  "utf8",
);

describe("<Link /> source contract", () => {
  it("uses cva for variant definitions", () => {
    expect(linkSource).toContain("cva(");
    expect(linkSource).toContain("variants:");
  });

  it("dispatches polymorphically: <a> when href is set, <button> otherwise", () => {
    expect(linkSource).toContain("<a");
    expect(linkSource).toContain("<button");
    expect(linkSource).toMatch(/href\s*!==\s*undefined/);
  });

  it("defaults the button form to type=button", () => {
    expect(linkSource).toContain('type="button"');
  });

  it("forwards arbitrary props (target, rel, disabled, etc.) to the underlying element", () => {
    expect(linkSource).toMatch(/\{\.\.\.\(rest\b/);
  });

  it("merges caller class via cn() helper", () => {
    expect(linkSource).toContain("cn(");
    expect(linkSource).toContain("variantProps.class");
  });

  it("default variant uses text-primary with underline-offset-4 and hover underline", () => {
    expect(linkSource).toContain("text-primary");
    expect(linkSource).toContain("underline-offset-4");
    expect(linkSource).toContain("hover:underline");
  });

  it("muted variant matches inline-body-copy drift site (underline + hover:text-foreground)", () => {
    expect(linkSource).toMatch(/muted:[\s\S]*hover:text-foreground/);
    expect(linkSource).toMatch(/muted:[\s\S]*underline-offset-4/);
  });

  it("size sm = text-xs (sidebar drift case), default = text-sm", () => {
    expect(linkSource).toMatch(/sm:\s*"text-xs"/);
    expect(linkSource).toMatch(/default:\s*"text-sm"/);
  });

  it("includes focus-visible ring and disabled affordances on the base", () => {
    expect(linkSource).toContain("focus-visible:ring");
    expect(linkSource).toContain("disabled:opacity-50");
    expect(linkSource).toContain("disabled:cursor-not-allowed");
  });

  it("uses tailwind tokens only (no inline hex)", () => {
    expect(linkSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });

  it("tags rendered element with data-slot=\"link\" for design-system attribution", () => {
    expect(linkSource).toContain('data-slot="link"');
  });
});

describe("<Link /> module surface", () => {
  it("exports Link as a function component", () => {
    expect(typeof Link).toBe("function");
  });

  it("exports linkVariants for downstream extension", () => {
    expect(typeof linkVariants).toBe("function");
    const cls = linkVariants({ variant: "default", size: "default" });
    expect(cls).toContain("text-primary");
    expect(cls).toContain("text-sm");
  });

  it("linkVariants applies muted variant classes", () => {
    const cls = linkVariants({ variant: "muted", size: "default" });
    expect(cls).toContain("hover:text-foreground");
    expect(cls).toContain("underline-offset-4");
    expect(cls).not.toContain("text-primary");
  });

  it("linkVariants size=sm applies text-xs", () => {
    const cls = linkVariants({ variant: "default", size: "sm" });
    expect(cls).toContain("text-xs");
  });

  it("linkVariants defaults are default + default", () => {
    const cls = linkVariants({});
    expect(cls).toContain("text-primary");
    expect(cls).toContain("text-sm");
  });

  it("LinkProps anchor form requires href and accepts target/rel", () => {
    const anchorProps: LinkProps = {
      href: "https://example.com",
      target: "_blank",
      rel: "noopener noreferrer",
      children: "Out",
    };
    expect(anchorProps.href).toBe("https://example.com");
  });

  it("LinkProps button form omits href and accepts disabled", () => {
    const buttonProps: LinkProps = {
      disabled: true,
      onClick: () => {},
      children: "Retry",
    };
    expect(buttonProps.disabled).toBe(true);
  });

  it("LinkProps accepts variant and size", () => {
    const props: LinkProps = {
      href: "/x",
      variant: "muted",
      size: "sm",
      children: "Inline",
    };
    expect(props.variant).toBe("muted");
    expect(props.size).toBe("sm");
  });
});
