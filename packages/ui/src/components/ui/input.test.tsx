import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("<Input /> invalid styling", () => {
  const inputSource = readFileSync(
    resolve("src/components/ui/input.tsx"),
    "utf8",
  );

  it("does not use presence-based aria-invalid styling", () => {
    expect(inputSource).not.toContain("aria-[invalid]:border-destructive");
    expect(inputSource).not.toContain("aria-[invalid]:ring-destructive");
  });

  it("uses true-specific aria-invalid styling", () => {
    expect(inputSource).toContain("aria-[invalid=true]:border-destructive");
    expect(inputSource).toContain("aria-[invalid=true]:ring-destructive/30");
  });
});
