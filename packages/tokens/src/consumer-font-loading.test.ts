import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ARCHIVE_FONT_CDN_URL, ARCHIVE_FONT_FAMILY } from "./archive-fonts";

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

describe("IBM Plex Sans Condensed", () => {
  it("declares the Condensed family in the CDN entry point", () => {
    const cdnCss = readWorkspaceFile("packages/tokens/src/fonts-cdn.css");

    expect(cdnCss).toContain("IBM+Plex+Sans+Condensed");
  });

  it("declares all 10 Condensed weights in the self-hosted entry point", () => {
    const selfHostedCss = readWorkspaceFile(
      "packages/tokens/src/fonts-self-hosted.css",
    );

    const expectedFiles = [
      "300.css",
      "400.css",
      "500.css",
      "600.css",
      "700.css",
      "300-italic.css",
      "400-italic.css",
      "500-italic.css",
      "600-italic.css",
      "700-italic.css",
    ];

    for (const file of expectedFiles) {
      expect(selfHostedCss).toContain(
        `@import "@fontsource/ibm-plex-sans-condensed/${file}";`,
      );
    }
  });

  it("declares the Condensed package as an optional peer dependency", () => {
    const pkgRaw = readWorkspaceFile("packages/tokens/package.json");
    const pkg = JSON.parse(pkgRaw) as {
      peerDependencies?: Record<string, string>;
      peerDependenciesMeta?: Record<string, { optional?: boolean }>;
    };

    expect(pkg.peerDependencies?.["@fontsource/ibm-plex-sans-condensed"]).toBeDefined();
    expect(
      pkg.peerDependenciesMeta?.["@fontsource/ibm-plex-sans-condensed"]?.optional,
    ).toBe(true);
  });
});

describe("archive font specification (single source of truth)", () => {
  it("ARCHIVE_FONT_CDN_URL matches the IBM Plex Sans Condensed @import in fonts-cdn.css", () => {
    const cdnCss = readWorkspaceFile("packages/tokens/src/fonts-cdn.css");

    expect(cdnCss).toContain(ARCHIVE_FONT_CDN_URL);
  });

  it("ARCHIVE_FONT_FAMILY is the Condensed family name", () => {
    expect(ARCHIVE_FONT_FAMILY).toBe("'IBM Plex Sans Condensed'");
  });

  it("exports archive-fonts from package.json", () => {
    const pkgRaw = readWorkspaceFile("packages/tokens/package.json");
    const pkg = JSON.parse(pkgRaw) as {
      exports?: Record<string, string>;
    };

    expect(pkg.exports?.["./archive-fonts"]).toBe("./src/archive-fonts.ts");
  });
});
