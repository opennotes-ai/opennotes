import { describe, expect, it } from "vitest";
import type { components } from "~/lib/generated-types";
import weatherLabelsJson from "./weather-labels.json";
import { VARIANT_CLASSES, VARIANT_HEX, AXIS_DEFINITIONS } from "./weather-labels";

const VALID_AXES = new Set(["truth", "relevance", "sentiment", "safety"] as const);
const VALID_VARIANTS = new Set(Object.keys(VARIANT_CLASSES));

type WeatherAxisTruth = components["schemas"]["WeatherAxisTruth"];
type WeatherAxisRelevance = components["schemas"]["WeatherAxisRelevance"];

const TRUTH_SLUGS = [
  "sourced",
  "factual_claims",
  "first_person",
  "hearsay",
  "misleading",
] as const satisfies ReadonlyArray<WeatherAxisTruth["label"]>;

type _TruthExhaustive =
  Exclude<WeatherAxisTruth["label"], (typeof TRUTH_SLUGS)[number]> extends never
    ? true
    : never;
const _truthExhaustive: _TruthExhaustive = true;

const RELEVANCE_SLUGS = [
  "insightful",
  "on_topic",
  "chatty",
  "drifting",
  "off_topic",
] as const satisfies ReadonlyArray<WeatherAxisRelevance["label"]>;

type _RelevanceExhaustive =
  Exclude<WeatherAxisRelevance["label"], (typeof RELEVANCE_SLUGS)[number]> extends never
    ? true
    : never;
const _relevanceExhaustive: _RelevanceExhaustive = true;

const SENTIMENT_SLUGS = [
  "supportive",
  "neutral",
  "critical",
  "oppositional",
] as const;

const SAFETY_SLUGS = [
  "safe",
  "mild",
  "caution",
  "unsafe",
] as const;

const ALL_EXPECTED_SLUGS: ReadonlyArray<string> = [
  ...TRUTH_SLUGS,
  ...RELEVANCE_SLUGS,
  ...SENTIMENT_SLUGS,
  ...SAFETY_SLUGS,
];

const NON_VARIANT_KEYS = new Set(["variant_hex_colors", "axis_definitions"]);
const JSON_KEYS = Object.keys(weatherLabelsJson).filter((k) => !NON_VARIANT_KEYS.has(k));

describe("weather-labels JSON drift guard", () => {
  it("every truth slug has a JSON entry", () => {
    for (const slug of TRUTH_SLUGS) {
      expect(
        JSON_KEYS,
        `Missing JSON entry for truth slug "${slug}"`,
      ).toContain(slug);
    }
  });

  it("every relevance slug has a JSON entry", () => {
    for (const slug of RELEVANCE_SLUGS) {
      expect(
        JSON_KEYS,
        `Missing JSON entry for relevance slug "${slug}"`,
      ).toContain(slug);
    }
  });

  it("every sentiment palette slug has a JSON entry", () => {
    for (const slug of SENTIMENT_SLUGS) {
      expect(
        JSON_KEYS,
        `Missing JSON entry for sentiment slug "${slug}"`,
      ).toContain(slug);
    }
  });

  it("JSON keys exactly match expected closed slugs — no extra, no missing", () => {
    const sorted = [...JSON_KEYS].sort();
    const expected = [...ALL_EXPECTED_SLUGS].sort();
    expect(sorted).toEqual(expected);
  });

  it("every JSON entry specifies an axis field", () => {
    for (const slug of JSON_KEYS) {
      const entry = (weatherLabelsJson as Record<string, unknown>)[slug];
      expect(
        (entry as Record<string, unknown>)["axis"],
        `JSON entry "${slug}" is missing an axis field`,
      ).toBeDefined();
    }
  });

  it("every JSON entry specifies a label field", () => {
    for (const slug of JSON_KEYS) {
      const entry = (weatherLabelsJson as Record<string, unknown>)[slug];
      expect(
        (entry as Record<string, unknown>)["label"],
        `JSON entry "${slug}" is missing a label field`,
      ).toBeDefined();
    }
  });

  it("every JSON entry specifies a variant field", () => {
    for (const slug of JSON_KEYS) {
      const entry = (weatherLabelsJson as Record<string, unknown>)[slug];
      expect(
        (entry as Record<string, unknown>)["variant"],
        `JSON entry "${slug}" is missing a variant field`,
      ).toBeDefined();
    }
  });

  it("every JSON entry has a valid axis value", () => {
    for (const slug of JSON_KEYS) {
      const entry = (weatherLabelsJson as Record<string, unknown>)[slug];
      const axis = (entry as Record<string, unknown>)["axis"] as string;
      expect(
        VALID_AXES.has(axis as "truth" | "relevance" | "sentiment" | "safety"),
        `JSON entry "${slug}" has invalid axis "${axis}" — must be one of: ${[...VALID_AXES].join(", ")}`,
      ).toBe(true);
    }
  });

  it("every JSON entry has a valid variant value that maps to a VARIANT_CLASSES key", () => {
    for (const slug of JSON_KEYS) {
      const entry = (weatherLabelsJson as Record<string, unknown>)[slug];
      const variant = (entry as Record<string, unknown>)["variant"] as string;
      expect(
        VALID_VARIANTS.has(variant),
        `JSON entry "${slug}" has invalid variant "${variant}" — must be one of: ${[...VALID_VARIANTS].join(", ")}`,
      ).toBe(true);
    }
  });
});

describe("weather-labels variant_hex_colors drift guard", () => {
  const VALID_VARIANT_KEYS = Object.keys(VARIANT_CLASSES);

  it("variant_hex_colors section exists in the JSON", () => {
    expect(weatherLabelsJson.variant_hex_colors).toBeDefined();
    expect(typeof weatherLabelsJson.variant_hex_colors).toBe("object");
  });

  it("every VARIANT_CLASSES key has a hex color in variant_hex_colors", () => {
    for (const variant of VALID_VARIANT_KEYS) {
      expect(
        (weatherLabelsJson.variant_hex_colors as Record<string, unknown>)[variant],
        `Missing variant_hex_colors entry for variant "${variant}"`,
      ).toBeDefined();
    }
  });

  it("every variant_hex_colors entry corresponds to a known VARIANT_CLASSES key", () => {
    for (const variant of Object.keys(weatherLabelsJson.variant_hex_colors)) {
      expect(
        VALID_VARIANTS.has(variant),
        `variant_hex_colors has unknown variant key "${variant}"`,
      ).toBe(true);
    }
  });

  it("every hex color in variant_hex_colors is a valid 3 or 6-digit hex string", () => {
    for (const [variant, hex] of Object.entries(weatherLabelsJson.variant_hex_colors)) {
      expect(
        /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(hex),
        `variant_hex_colors["${variant}"] = "${hex}" is not a valid hex color`,
      ).toBe(true);
    }
  });

  it("VARIANT_HEX exported from weather-labels.ts matches JSON", () => {
    for (const [variant, hex] of Object.entries(weatherLabelsJson.variant_hex_colors)) {
      expect(
        (VARIANT_HEX as Record<string, string>)[variant],
        `VARIANT_HEX["${variant}"] does not match JSON`,
      ).toBe(hex);
    }
  });
});

describe("weather-labels axis_definitions drift guard", () => {
  const VALID_AXIS_KEYS = ["truth", "relevance", "sentiment", "safety"];

  it("axis_definitions section exists in the JSON", () => {
    expect(weatherLabelsJson.axis_definitions).toBeDefined();
    expect(typeof weatherLabelsJson.axis_definitions).toBe("object");
  });

  it("every axis has an entry in axis_definitions", () => {
    for (const axis of VALID_AXIS_KEYS) {
      expect(
        (weatherLabelsJson.axis_definitions as Record<string, unknown>)[axis],
        `Missing axis_definitions entry for axis "${axis}"`,
      ).toBeDefined();
    }
  });

  it("every axis_definitions entry has a heading string", () => {
    for (const [axis, def] of Object.entries(weatherLabelsJson.axis_definitions)) {
      expect(
        typeof (def as Record<string, unknown>)["heading"],
        `axis_definitions["${axis}"].heading must be a string`,
      ).toBe("string");
    }
  });

  it("every axis_definitions entry has a description string", () => {
    for (const [axis, def] of Object.entries(weatherLabelsJson.axis_definitions)) {
      expect(
        typeof (def as Record<string, unknown>)["description"],
        `axis_definitions["${axis}"].description must be a string`,
      ).toBe("string");
    }
  });

  it("axis_definitions has no unknown axes beyond the four valid ones", () => {
    for (const axis of Object.keys(weatherLabelsJson.axis_definitions)) {
      expect(
        VALID_AXIS_KEYS.includes(axis),
        `axis_definitions has unknown axis key "${axis}"`,
      ).toBe(true);
    }
  });

  it("AXIS_DEFINITIONS exported from weather-labels.ts matches JSON", () => {
    for (const axis of VALID_AXIS_KEYS) {
      const jsonDef = (weatherLabelsJson.axis_definitions as Record<string, { heading: string; description: string }>)[axis];
      expect(AXIS_DEFINITIONS[axis as "truth" | "relevance" | "sentiment" | "safety"]).toEqual(jsonDef);
    }
  });
});
