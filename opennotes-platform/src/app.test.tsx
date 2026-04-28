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

  it("renders Sign In CTA pointing at /login when no user", () => {
    expect(appSource).toContain('href="/login"');
    expect(appSource).toContain("Sign In");
  });

  it("renders mode-toggle in the actions slot", () => {
    expect(appSource).toContain("<ModeToggle");
  });

  it("does not retain the legacy placeholder span", () => {
    expect(appSource).not.toContain("Open Notes Platform</span>");
  });

  it("reads auth state on the server via getUser query (no client-only auth)", () => {
    expect(appSource).toContain('from "~/lib/supabase-server"');
    expect(appSource).toContain("getUser");
    expect(appSource).toMatch(/query\(\s*async\s*\(\)\s*=>\s*\{/);
    expect(appSource).toContain('"use server"');
    expect(appSource).toContain("createAsync(");
  });

  it("renders a Sign Out form posting to /auth/signout when user is present", () => {
    expect(appSource).toContain('action="/auth/signout"');
    expect(appSource).toContain('method="post"');
    expect(appSource).toContain("Sign Out");
    expect(appSource).toMatch(/<button[^>]*type="submit"/);
  });

  it("toggles between Sign In and Sign Out via <Show> on the auth signal", () => {
    expect(appSource).toMatch(/<Show\b[^>]*\bwhen=\{[^}]*\(\)\}/);
    expect(appSource).toMatch(/fallback=\{[^]*Sign In/);
  });

  it("keeps ModeToggle outside the auth-aware Show so it renders in both states", () => {
    const modeToggleIdx = appSource.indexOf("<ModeToggle");
    const showIdx = appSource.indexOf("<Show");
    expect(modeToggleIdx).toBeGreaterThan(-1);
    expect(showIdx).toBeGreaterThan(-1);
    expect(modeToggleIdx).toBeLessThan(showIdx);
  });
});
