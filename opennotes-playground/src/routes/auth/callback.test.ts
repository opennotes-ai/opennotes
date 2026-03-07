import { describe, expect, it } from "vitest";
import { safeRedirectPath } from "../../lib/safe-redirect";

describe("safeRedirectPath", () => {
  it("returns / for null", () => {
    expect(safeRedirectPath(null)).toBe("/");
  });

  it("returns / for empty string", () => {
    expect(safeRedirectPath("")).toBe("/");
  });

  it("returns / for protocol-relative URL (//evil.com)", () => {
    expect(safeRedirectPath("//evil.com")).toBe("/");
  });

  it("returns / for backslash URL (\\evil.com)", () => {
    expect(safeRedirectPath("\\evil.com")).toBe("/");
  });

  it("returns / for embedded :// (http://evil.com)", () => {
    expect(safeRedirectPath("http://evil.com")).toBe("/");
  });

  it("returns / for https:// URL", () => {
    expect(safeRedirectPath("https://evil.com")).toBe("/");
  });

  it("allows valid absolute path /dashboard", () => {
    expect(safeRedirectPath("/dashboard")).toBe("/dashboard");
  });

  it("allows root path /", () => {
    expect(safeRedirectPath("/")).toBe("/");
  });

  it("allows nested path /a/b/c", () => {
    expect(safeRedirectPath("/a/b/c")).toBe("/a/b/c");
  });

  it("returns / for path with :// embedded after slash", () => {
    expect(safeRedirectPath("/foo://bar")).toBe("/");
  });
});
