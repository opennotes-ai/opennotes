import { describe, expect, it } from "vitest";
import {
  formatIdBadgeLabel,
  formatIdBadgeTooltip,
  isUuidLike,
  proquintToHexSuffix,
  resolveAnchorId,
} from "./format";

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
});

describe("proquint reverse lookup", () => {
  const UUID_SAMPLE = "0195a3bc-3dc8-7f2b-9e07-c4e21c0f5a10";

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
    const label = formatIdBadgeLabel(items[0].id);
    const result = resolveAnchorId(`note-${label}`, items, "note");
    expect(result).toBe(items[0].id);
  });

  it("returns null for non-matching input", () => {
    expect(resolveAnchorId("note-nonexistent", items, "note")).toBeNull();
  });

  it("returns null for empty items", () => {
    expect(resolveAnchorId("note-abc", [], "note")).toBeNull();
  });
});
