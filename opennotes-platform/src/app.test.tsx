import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const appSource = readFileSync(resolve("src/app.tsx"), "utf8");

describe("global app shell", () => {
  it("imports NavBar and ModeToggle from @opennotes/ui", () => {
    expect(appSource).toContain('from "@opennotes/ui/components/nav-bar"');
    expect(appSource).toContain('from "@opennotes/ui/components/mode-toggle"');
  });

  it("renders the Open Notes logo image at h-9 w-auto", () => {
    expect(appSource).toContain('src="/opennotes-logo.svg"');
    expect(appSource).toContain('alt="Open Notes"');
    expect(appSource).toContain('class="h-9 w-auto"');
  });

  it("includes a Docs link to docs.opennotes.ai (same tab)", () => {
    expect(appSource).toContain("https://docs.opennotes.ai");
    expect(appSource).toContain('label: "Docs"');
    expect(appSource).not.toContain('external: true');
  });

  it("renders Sign In CTA pointing at /login", () => {
    expect(appSource).toContain('href="/login"');
    expect(appSource).toContain("Sign In");
  });

  it("renders mode-toggle in the actions slot", () => {
    expect(appSource).toContain("<ModeToggle");
  });

  it("does not retain the legacy placeholder span", () => {
    expect(appSource).not.toContain("Open Notes Platform</span>");
  });
});
