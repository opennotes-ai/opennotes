import { describe, expect, it } from "vitest";
import { formatWeatherLabel } from "./weather-labels";

describe("formatWeatherLabel", () => {
  it("returns 'Mostly Factual' for mostly_factual", () => {
    expect(formatWeatherLabel("mostly_factual")).toBe("Mostly Factual");
  });

  it("returns 'Self Reported' for self_reported (no explicit case; default title-caser)", () => {
    expect(formatWeatherLabel("self_reported")).toBe("Self Reported");
  });

  it("returns 'On topic' for on_topic", () => {
    expect(formatWeatherLabel("on_topic")).toBe("On topic");
  });

  it("returns 'Off topic' for off_topic", () => {
    expect(formatWeatherLabel("off_topic")).toBe("Off topic");
  });

  it("returns 'Factual claims' for factual_claims (AC9)", () => {
    expect(formatWeatherLabel("factual_claims")).toBe("Factual claims");
  });

  it("returns 'First-person' for first_person (AC9)", () => {
    expect(formatWeatherLabel("first_person")).toBe("First-person");
  });
});
