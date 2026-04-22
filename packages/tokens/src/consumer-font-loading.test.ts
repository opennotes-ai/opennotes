import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

function readWorkspaceFile(path: string): string {
  return readFileSync(resolve(repoRoot, path), "utf8");
}

describe("first-party token font loading", () => {
  it("requires web app token consumers to import CDN fonts explicitly", () => {
    const platformCss = readWorkspaceFile("opennotes-platform/src/app.css");
    const playgroundCss = readWorkspaceFile("opennotes-playground/src/app.css");
    const vibecheckCss = readWorkspaceFile("opennotes-vibecheck-web/src/app.css");

    expect(platformCss).toContain('@import "@opennotes/tokens";');
    expect(platformCss).toContain(
      '@import "@opennotes/tokens/fonts-cdn.css";',
    );
    expect(playgroundCss).toContain('@import "@opennotes/tokens";');
    expect(playgroundCss).toContain(
      '@import "@opennotes/tokens/fonts-cdn.css";',
    );
    expect(vibecheckCss).toContain('@import "@opennotes/tokens";');
    expect(vibecheckCss).toContain(
      '@import "@opennotes/tokens/fonts-cdn.css";',
    );
  });

  it("keeps docs on the vendored CDN font entry point", () => {
    const docsCss = readWorkspaceFile("opennotes-docs/style.css");

    expect(docsCss).toContain('@import "./styles/tokens/fonts-cdn.css";');
  });

  it("does not duplicate Google Fonts links from Solid entry servers", () => {
    const platformEntry = readWorkspaceFile("opennotes-platform/src/entry-server.tsx");
    const playgroundEntry = readWorkspaceFile("opennotes-playground/src/entry-server.tsx");
    const vibecheckEntry = readWorkspaceFile("opennotes-vibecheck-web/src/entry-server.tsx");

    expect(platformEntry).not.toContain("fonts.googleapis.com");
    expect(playgroundEntry).not.toContain("fonts.googleapis.com");
    expect(vibecheckEntry).not.toContain("fonts.googleapis.com");
  });
});
