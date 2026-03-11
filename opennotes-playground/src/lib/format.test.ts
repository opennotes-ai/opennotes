import { describe, expect, it } from "vitest";
import {
  formatIdBadgeLabel,
  formatIdBadgeTooltip,
  isUuidLike,
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
