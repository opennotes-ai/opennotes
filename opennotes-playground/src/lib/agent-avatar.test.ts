import { describe, it, expect } from "vitest";
import { getAgentAvatar } from "./agent-avatar";

describe("getAgentAvatar", () => {
  it("returns emoji and bgColor", () => {
    const result = getAgentAvatar("01234567-89ab-cdef-0123-a1b2c3d4e5f6");
    expect(result).toHaveProperty("emoji");
    expect(result).toHaveProperty("bgColor");
    expect(typeof result.emoji).toBe("string");
    expect(typeof result.bgColor).toBe("string");
  });

  it("is deterministic - same ID returns same result", () => {
    const id = "01234567-89ab-cdef-0123-a1b2c3d4e5f6";
    const r1 = getAgentAvatar(id);
    const r2 = getAgentAvatar(id);
    expect(r1).toEqual(r2);
  });

  it("produces varied results for different IDs", () => {
    const ids = [
      "00000000-0000-0000-0000-000000000001",
      "00000000-0000-0000-0000-000000000002",
      "00000000-0000-0000-0000-abcdef123456",
    ];
    const results = ids.map(getAgentAvatar);
    const unique = new Set(results.map((r) => `${r.emoji}-${r.bgColor}`));
    expect(unique.size).toBeGreaterThan(1);
  });

  it("bgColor is a valid Tailwind class", () => {
    const result = getAgentAvatar("01234567-89ab-cdef-0123-a1b2c3d4e5f6");
    expect(result.bgColor).toMatch(/^bg-[a-z]+-\d+$/);
  });
});
