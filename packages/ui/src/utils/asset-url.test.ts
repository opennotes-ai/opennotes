import { describe, expect, it } from "vitest";
import { getAssetUrl } from "./asset-url";

describe("getAssetUrl", () => {
  it("returns GCS URL for opennotes-logo.svg", () => {
    expect(getAssetUrl("opennotes-logo.svg")).toBe(
      "https://storage.googleapis.com/open-notes-core-public-assets/opennotes-logo.svg"
    );
  });

  it("returns GCS URL for favicon.ico", () => {
    expect(getAssetUrl("favicon.ico")).toBe(
      "https://storage.googleapis.com/open-notes-core-public-assets/favicon.ico"
    );
  });

  it("returns GCS URL for og-default.png", () => {
    expect(getAssetUrl("og-default.png")).toBe(
      "https://storage.googleapis.com/open-notes-core-public-assets/og-default.png"
    );
  });
});
