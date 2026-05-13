import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { Footer } from "./footer";

describe("<Footer /> source contract", () => {
  const footerSource = readFileSync(
    resolve("src/components/footer.tsx"),
    "utf8",
  );

  it("uses token classes (no inline hex colors)", () => {
    expect(footerSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });

  it("uses border-border + bg-background tokens", () => {
    expect(footerSource).toContain("border-border");
    expect(footerSource).toContain("bg-background");
  });

  it("includes privacy policy link to /privacy", () => {
    expect(footerSource).toContain("https://opennotes.ai/privacy");
    expect(footerSource).toContain("Privacy");
  });

  it("includes terms link to /terms", () => {
    expect(footerSource).toContain("https://opennotes.ai/terms");
    expect(footerSource).toContain("Terms");
  });

  it("uses dynamic year via new Date().getFullYear()", () => {
    expect(footerSource).toContain("new Date().getFullYear()");
  });

  it("includes Open Notes copyright text", () => {
    expect(footerSource).toContain("Open Notes");
  });

  it("policy links open externally with target=_blank and rel=noopener noreferrer", () => {
    expect(footerSource).toContain('target="_blank"');
    expect(footerSource).toContain('rel="noopener noreferrer"');
  });

  it("uses footer element for semantic HTML", () => {
    expect(footerSource).toContain("<footer");
  });

  it("does not access window/document at module top level (SSR-safe)", () => {
    const beforeExport = footerSource.split("export function Footer")[0];
    expect(beforeExport).not.toMatch(/\bwindow\./);
    expect(beforeExport).not.toMatch(/\bdocument\./);
  });

  it("does not use @kobalte/core directly", () => {
    expect(footerSource).not.toContain("@kobalte/core");
  });
});

describe("<Footer /> module surface", () => {
  it("exports the Footer component as a function", () => {
    expect(typeof Footer).toBe("function");
  });
});
