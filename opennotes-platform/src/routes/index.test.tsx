import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const indexSource = readFileSync(resolve("src/routes/index.tsx"), "utf8");

describe("/ landing page composition", () => {
  it("imports primitives from @opennotes/ui (not local one-offs)", () => {
    expect(indexSource).toContain('from "@opennotes/ui/components/marketing-hero"');
    expect(indexSource).toContain('from "@opennotes/ui/components/steps-list"');
    expect(indexSource).toContain('from "@opennotes/ui/components/audience-card"');
  });

  it("renders the marketing hero with kicker, headline, body, and CTAs", () => {
    expect(indexSource).toContain('kicker="Open Notes Platform"');
    expect(indexSource).toContain("Community-powered moderation");
    expect(indexSource).toContain('href="/register"');
    expect(indexSource).toContain("https://docs.opennotes.ai");
    expect(indexSource).toContain("Get started");
    expect(indexSource).toContain("Read the docs");
  });

  it("includes all 5 'Get started in minutes' step titles", () => {
    expect(indexSource).toContain("Create your account");
    expect(indexSource).toContain("Generate your API key");
    expect(indexSource).toContain("Send your first request");
    expect(indexSource).toContain("Get results automatically");
    expect(indexSource).toContain("Plug into your workflow");
  });

  it("includes inline detail for first-request step (POST /api/public/v1/requests)", () => {
    expect(indexSource).toContain("POST /api/public/v1/requests");
  });

  it("renders three audience cards with correct deep links", () => {
    expect(indexSource).toContain(
      "https://docs.opennotes.ai/existing-integrations/discourse/overview",
    );
    expect(indexSource).toContain(
      "https://docs.opennotes.ai/integration-guide/overview",
    );
    expect(indexSource).toContain(
      "https://docs.opennotes.ai/api-reference/overview",
    );
  });

  it("audience cards use AudienceCard primitive (which defaults to same-tab)", () => {
    expect(indexSource).toContain("<AudienceCard");
    expect(indexSource).not.toContain('target="_blank"');
  });

  it("renders final CTA strip with Sign Up and Sign In", () => {
    expect(indexSource).toContain("Ready to ship?");
    expect(indexSource).toContain("Sign Up");
    expect(indexSource).toContain("Sign In");
    expect(indexSource).toContain('href="/login"');
  });

  it("uses token classes only (no inline hex colors)", () => {
    expect(indexSource).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(indexSource).toContain("text-foreground");
    expect(indexSource).toContain("text-muted-foreground");
    expect(indexSource).toContain("border-border");
  });

  it("does not retain the legacy centered hero markup", () => {
    expect(indexSource).not.toContain(
      'class="mx-auto max-w-2xl px-4 py-16 text-center"',
    );
  });

  it("preserves the redirectIfAuthenticated wiring on /", () => {
    expect(indexSource).toContain("redirectIfAuthenticated");
    expect(indexSource).toContain('"landing-redirect"');
    expect(indexSource).toContain("preload");
  });

  it("does not use forbidden visual treatments", () => {
    expect(indexSource).not.toMatch(/border-l-\[/);
    expect(indexSource).not.toMatch(/border-r-\[/);
    expect(indexSource).not.toMatch(/bg-gradient-to-/);
    expect(indexSource).not.toMatch(/text-transparent/);
  });
});
