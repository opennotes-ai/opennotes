import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
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

  it("does not access window/document anywhere in module (SSR-safe)", () => {
    expect(footerSource).not.toMatch(/\bwindow\./);
    expect(footerSource).not.toMatch(/\bdocument\./);
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

describe("<Footer /> render behavior", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders copyright text with the current year", () => {
    render(() => <Footer />);
    expect(screen.getByText(new RegExp(String(new Date().getFullYear())))).toBeTruthy();
  });

  it("renders Privacy link pointing to opennotes.ai/privacy", () => {
    const { container } = render(() => <Footer />);
    const link = container.querySelector('a[href="https://opennotes.ai/privacy"]');
    expect(link).toBeTruthy();
    expect(link?.textContent).toContain("Privacy");
  });

  it("renders Terms link pointing to opennotes.ai/terms", () => {
    const { container } = render(() => <Footer />);
    const link = container.querySelector('a[href="https://opennotes.ai/terms"]');
    expect(link).toBeTruthy();
    expect(link?.textContent).toContain("Terms");
  });

  it("policy links open externally with noopener noreferrer", () => {
    const { container } = render(() => <Footer />);
    const links = container.querySelectorAll('a[target="_blank"]');
    expect(links.length).toBe(2);
    for (const link of Array.from(links)) {
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });

  it("renders a footer landmark element", () => {
    const { container } = render(() => <Footer />);
    expect(container.querySelector("footer")).toBeTruthy();
  });
});
