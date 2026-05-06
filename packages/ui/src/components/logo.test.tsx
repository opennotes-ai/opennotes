import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { Logo } from "./logo";

describe("<Logo /> source contract", () => {
  const logoSource = readFileSync(resolve("src/components/logo.tsx"), "utf8");

  it("renders img with canonical GCS logo URL", () => {
    expect(logoSource).toContain("opennotes-logo.svg");
    expect(logoSource).toContain("getAssetUrl");
  });

  it("defaults alt to Open Notes", () => {
    expect(logoSource).toContain('"Open Notes"');
  });

  it("passes class prop through to img", () => {
    expect(logoSource).toContain("props.class");
  });
});

describe("<Logo /> module surface", () => {
  it("exports Logo as a function", () => {
    expect(typeof Logo).toBe("function");
  });
});
