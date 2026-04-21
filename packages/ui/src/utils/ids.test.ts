import { describe, expect, it } from "vitest";
import {
  formatIdBadgeLabel,
  formatIdBadgeTooltip,
  isUuidLike,
  proquintToHexSuffix,
  resolveAnchorId,
} from "./ids";

const UUID_SAMPLE = "0195a3bc-3dc8-7f2b-9e07-c4e21c0f5a10";

describe("id badge formatting", () => {
  it("uses UUID suffix label for UUID values", () => {
    const label = formatIdBadgeLabel(UUID_SAMPLE);
    expect(label).not.toBe("0195a3bc");
    expect(label).toMatch(/^[a-z]{5}-[a-z]{5}$/);
  });

  it("returns two-line tooltip for UUID values", () => {
    const tooltip = formatIdBadgeTooltip(UUID_SAMPLE);
    expect(tooltip).toContain("\n");
    const [line1, line2] = tooltip.split("\n");
    expect(line1).toMatch(/^[a-z]{5}-[a-z]{5}$/);
    expect(line2).toBe(UUID_SAMPLE);
    expect(tooltip.split("\n")).toHaveLength(2);
  });

  it("passes non-UUID strings through", () => {
    expect(formatIdBadgeLabel("ungrouped")).toBe("ungrouped");
    expect(formatIdBadgeTooltip("ungrouped")).toBe("ungrouped");
    expect(isUuidLike("ungrouped")).toBe(false);
  });

  it("renders null and undefined as <Unspecified>", () => {
    expect(formatIdBadgeLabel(null)).toBe("<Unspecified>");
    expect(formatIdBadgeTooltip(undefined)).toBe("<Unspecified>");
  });

  it("returns name as label when name is provided", () => {
    expect(formatIdBadgeLabel(UUID_SAMPLE, "My Run")).toBe("My Run");
  });

  it("falls back to proquint when name is null", () => {
    const withNull = formatIdBadgeLabel(UUID_SAMPLE, null);
    const withoutName = formatIdBadgeLabel(UUID_SAMPLE);
    expect(withNull).toBe(withoutName);
    expect(withNull).toMatch(/^[a-z]{5}-[a-z]{5}$/);
  });

  it("falls back to proquint when name is undefined", () => {
    const withUndef = formatIdBadgeLabel(UUID_SAMPLE, undefined);
    expect(withUndef).toMatch(/^[a-z]{5}-[a-z]{5}$/);
  });

  it("falls back to proquint when name is empty string", () => {
    const withEmpty = formatIdBadgeLabel(UUID_SAMPLE, "");
    expect(withEmpty).toMatch(/^[a-z]{5}-[a-z]{5}$/);
  });

  it("returns three-line tooltip when name is provided", () => {
    const tooltip = formatIdBadgeTooltip(UUID_SAMPLE, "My Run");
    const lines = tooltip.split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe("My Run");
    expect(lines[1]).toMatch(/^[a-z]{5}-[a-z]{5}$/);
    expect(lines[2]).toBe(UUID_SAMPLE);
  });

  it("returns two-line tooltip when name is null", () => {
    const tooltip = formatIdBadgeTooltip(UUID_SAMPLE, null);
    const lines = tooltip.split("\n");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatch(/^[a-z]{5}-[a-z]{5}$/);
    expect(lines[1]).toBe(UUID_SAMPLE);
  });

  it("returns two-line tooltip when name is empty string", () => {
    const tooltip = formatIdBadgeTooltip(UUID_SAMPLE, "");
    const lines = tooltip.split("\n");
    expect(lines).toHaveLength(2);
  });
});

describe("proquint reverse lookup", () => {
  it("round-trips encode then decode for known UUID", () => {
    const label = formatIdBadgeLabel(UUID_SAMPLE);
    const hexSuffix = proquintToHexSuffix(label);
    const expectedSuffix = UUID_SAMPLE.replace(/-/g, "").slice(-8);
    expect(hexSuffix).toBe(expectedSuffix);
  });

  it("round-trips for multiple UUIDs", () => {
    const uuids = [
      "019ceaaf-1234-7000-8000-aabbccddeeff",
      "00000000-0000-4000-8000-000000000000",
      "ffffffff-ffff-4fff-bfff-ffffffffffff",
    ];
    for (const uuid of uuids) {
      const label = formatIdBadgeLabel(uuid);
      const hex = proquintToHexSuffix(label);
      expect(hex).toBe(uuid.replace(/-/g, "").slice(-8));
    }
  });
});

describe("resolveAnchorId", () => {
  const items = [
    { id: "0195a3bc-3dc8-7f2b-9e07-c4e21c0f5a10" },
    { id: "019ceaaf-1234-7000-8000-aabbccddeeff" },
  ];

  it("matches by full UUID", () => {
    const result = resolveAnchorId("note-0195a3bc-3dc8-7f2b-9e07-c4e21c0f5a10", items, "note");
    expect(result).toBe("0195a3bc-3dc8-7f2b-9e07-c4e21c0f5a10");
  });

  it("matches by proquint", () => {
    const label = formatIdBadgeLabel(items[0]!.id);
    const result = resolveAnchorId(`note-${label}`, items, "note");
    expect(result).toBe(items[0]!.id);
  });

  it("returns null for non-matching input", () => {
    expect(resolveAnchorId("note-nonexistent", [], "note")).toBeNull();
  });

  it("returns null for empty items", () => {
    expect(resolveAnchorId("note-abc", [], "note")).toBeNull();
  });
});
