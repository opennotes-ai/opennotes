import { describe, expect, it } from "vitest";
import { safetyLevel, lobeColors } from "./weather-symbol-derive";
import type { components } from "~/lib/generated-types";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type WeatherReport = components["schemas"]["WeatherReport"];

function makeReport(
  truthLabel: string,
  relevanceLabel: string,
  sentimentLabel: string,
): WeatherReport {
  return {
    truth: { label: truthLabel as WeatherReport["truth"]["label"] },
    relevance: { label: relevanceLabel as WeatherReport["relevance"]["label"] },
    sentiment: { label: sentimentLabel as WeatherReport["sentiment"]["label"] },
  };
}

function makeRec(level: string): SafetyRecommendation {
  return {
    level: level as SafetyRecommendation["level"],
    rationale: "test rationale",
  };
}

describe("safetyLevel", () => {
  it("returns 'safe' for a safe recommendation", () => {
    expect(safetyLevel(makeRec("safe"))).toBe("safe");
  });

  it("returns 'mild' for a mild recommendation", () => {
    expect(safetyLevel(makeRec("mild"))).toBe("mild");
  });

  it("returns 'caution' for a caution recommendation", () => {
    expect(safetyLevel(makeRec("caution"))).toBe("caution");
  });

  it("returns 'unsafe' for an unsafe recommendation", () => {
    expect(safetyLevel(makeRec("unsafe"))).toBe("unsafe");
  });

  it("returns 'unknown' for null", () => {
    expect(safetyLevel(null)).toBe("unknown");
  });

  it("returns 'unknown' for undefined", () => {
    expect(safetyLevel(undefined)).toBe("unknown");
  });
});

describe("lobeColors", () => {
  it("returns three hex strings for known labels", () => {
    const report = makeReport("misleading", "insightful", "supportive");
    const colors = lobeColors(report);
    expect(colors).toHaveLength(3);
    for (const color of colors) {
      expect(typeof color).toBe("string");
      expect(color).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it("returns [truth, relevance, sentiment] in order", () => {
    const reportA = makeReport("misleading", "insightful", "neutral");
    const reportB = makeReport("insightful", "misleading", "neutral");
    const colorsA = lobeColors(reportA);
    const colorsB = lobeColors(reportB);
    expect(colorsA[0]).not.toBe(colorsB[0]);
    expect(colorsA[1]).not.toBe(colorsB[1]);
  });

  it("handles axes with unknown labels without throwing", () => {
    const report = makeReport(
      "unknown_label_xyz" as WeatherReport["truth"]["label"],
      "another_unknown" as WeatherReport["relevance"]["label"],
      "yet_another" as WeatherReport["sentiment"]["label"],
    );
    expect(() => lobeColors(report)).not.toThrow();
    const colors = lobeColors(report);
    expect(colors).toHaveLength(3);
    for (const color of colors) {
      expect(typeof color).toBe("string");
    }
  });
});
