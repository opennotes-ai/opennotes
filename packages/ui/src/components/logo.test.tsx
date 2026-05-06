import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { Logo } from "./logo";
import { getAssetUrl } from "../utils/asset-url";

describe("<Logo /> source contract", () => {
  const logoSource = readFileSync(resolve("src/components/logo.tsx"), "utf8");

  it("renders img pointing to the canonical GCS logo via getAssetUrl", () => {
    expect(logoSource).toContain('getAssetUrl("opennotes-logo.svg")');
  });

  it("defaults alt to Open Notes", () => {
    expect(logoSource).toContain('"Open Notes"');
  });

  it("passes class prop through to img", () => {
    expect(logoSource).toContain("props.class");
  });
});

describe("<Logo /> URL contract", () => {
  it("getAssetUrl produces the correct logo src for Logo", () => {
    expect(getAssetUrl("opennotes-logo.svg")).toBe(
      "https://storage.googleapis.com/open-notes-core-public-assets/opennotes-logo.svg"
    );
  });
});

describe("<Logo /> module surface", () => {
  it("exports Logo as a function", () => {
    expect(typeof Logo).toBe("function");
  });
});
