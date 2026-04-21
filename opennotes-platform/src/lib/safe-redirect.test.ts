import { describe, expect, test } from "vitest";
import { safeRedirectPath } from "./safe-redirect";

describe("safeRedirectPath", () => {
  test("returns the provided same-origin path unchanged", () => {
    expect(safeRedirectPath("/dashboard")).toBe("/dashboard");
    expect(safeRedirectPath("/dashboard?tab=keys")).toBe("/dashboard?tab=keys");
  });

  test("falls back to / when value is missing", () => {
    expect(safeRedirectPath(null)).toBe("/");
    expect(safeRedirectPath("")).toBe("/");
  });

  test("rejects paths that do not start with a single slash", () => {
    expect(safeRedirectPath("dashboard")).toBe("/");
    expect(safeRedirectPath("https://evil.example.com")).toBe("/");
  });

  test("rejects protocol-relative and scheme-bearing targets", () => {
    expect(safeRedirectPath("//evil.example.com")).toBe("/");
    expect(safeRedirectPath("/redirect?u=https://evil.example.com")).toBe("/");
  });

  test("rejects backslash-escaped targets that some browsers treat as authority", () => {
    expect(safeRedirectPath("/\\evil.example.com")).toBe("/");
  });
});
