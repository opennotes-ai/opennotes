import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { NavBar, type NavBarItem, type NavBarProps } from "./nav-bar";

describe("<NavBar /> source contract", () => {
  const navBarSource = readFileSync(
    resolve("src/components/nav-bar.tsx"),
    "utf8",
  );

  it("uses token classes (no inline hex colors)", () => {
    expect(navBarSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });

  it("uses border-border + bg-background tokens, not raw colors", () => {
    expect(navBarSource).toContain("border-border");
    expect(navBarSource).toContain("bg-background");
  });

  it("nav links use text-foreground (marketing-site match)", () => {
    expect(navBarSource).toContain("text-foreground");
    expect(navBarSource).not.toContain("text-muted-foreground");
  });

  it("nav links use hover:text-primary (marketing-site match)", () => {
    expect(navBarSource).toContain("hover:text-primary");
    expect(navBarSource).not.toContain("hover:text-foreground");
  });

  it("nav links use whitespace-nowrap (marketing-site match)", () => {
    expect(navBarSource).toContain("whitespace-nowrap");
  });

  it("renders external links with target=_blank and rel=noopener noreferrer", () => {
    expect(navBarSource).toContain('target={item.external ? "_blank" : undefined}');
    expect(navBarSource).toContain(
      'rel={item.external ? "noopener noreferrer" : undefined}',
    );
  });

  it("defaults logoHref to '/' when not supplied", () => {
    expect(navBarSource).toContain('href={local.logoHref ?? "/"}');
  });

  it("does not introduce banned visual treatments", () => {
    expect(navBarSource).not.toMatch(/border-l-\[/);
    expect(navBarSource).not.toMatch(/border-r-\[/);
    expect(navBarSource).not.toMatch(/bg-gradient-to-/);
    expect(navBarSource).not.toMatch(/text-transparent/);
  });

  it("does not access window/document at module top level (SSR-safe)", () => {
    const beforeExport = navBarSource.split("export function NavBar")[0];
    expect(beforeExport).not.toMatch(/\bwindow\./);
    expect(beforeExport).not.toMatch(/\bdocument\./);
  });
});

describe("<NavBar /> module surface", () => {
  it("exports the NavBar component as a function", () => {
    expect(typeof NavBar).toBe("function");
  });

  it("exposes NavBarItem and NavBarProps types via named exports", () => {
    const item: NavBarItem = { label: "Docs", href: "/docs" };
    const externalItem: NavBarItem = {
      label: "Ext",
      href: "https://x",
      external: true,
    };
    const props: NavBarProps = {
      logo: null,
      items: [item, externalItem],
    };
    expect(item.label).toBe("Docs");
    expect(externalItem.external).toBe(true);
    expect(props.items?.length).toBe(2);
  });
});
