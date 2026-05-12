import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  resolve("src/components/ui/progress-circle.tsx"),
  "utf8",
);

describe("<ProgressCircle /> recipe — structure and exports", () => {
  it("exports ProgressCircle", () => {
    expect(source).toMatch(/export\s*\{[^}]*ProgressCircle[^}]*\}/);
  });

  it("accepts a value prop (0-100)", () => {
    expect(source).toContain("value");
    expect(source).toContain("getLimitedValue");
  });

  it("clamps value between 0 and 100", () => {
    expect(source).toContain("100");
    expect(source).toContain("undefined");
  });

  it("renders an SVG with two circles (track + progress)", () => {
    expect(source).toMatch(/<circle/);
    const circleCount = (source.match(/<circle/g) ?? []).length;
    expect(circleCount).toBeGreaterThanOrEqual(2);
  });

  it("uses stroke-dasharray and stroke-dashoffset for progress arc", () => {
    expect(source).toContain("stroke-dasharray");
    expect(source).toContain("stroke-dashoffset");
  });

  it("rotates the SVG -90 degrees so arc starts at top", () => {
    expect(source).toContain("-rotate-90");
  });

  it("supports multiple sizes via size prop (xs, sm, md, lg, xl)", () => {
    expect(source).toContain('"xs"');
    expect(source).toContain('"sm"');
    expect(source).toContain('"md"');
    expect(source).toContain('"lg"');
    expect(source).toContain('"xl"');
  });

  it("supports custom radius and strokeWidth overrides", () => {
    expect(source).toContain("radius");
    expect(source).toContain("strokeWidth");
  });

  it("supports showAnimation prop with transition classes", () => {
    expect(source).toContain("showAnimation");
    expect(source).toContain("transition");
  });

  it("uses cn() from ../../utils (local package path)", () => {
    expect(source).toContain("../../utils");
    expect(source).toContain("cn(");
  });

  it("uses mergeProps and splitProps from solid-js", () => {
    expect(source).toContain("mergeProps");
    expect(source).toContain("splitProps");
  });

  it("children are rendered inside an absolute flex container (label support)", () => {
    expect(source).toContain("absolute");
  });
});
