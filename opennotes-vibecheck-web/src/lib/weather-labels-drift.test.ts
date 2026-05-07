import { describe, expect, it } from "vitest";
import type { components } from "~/lib/generated-types";
import weatherLabelsJson from "./weather-labels.json";
import { VARIANT_CLASSES } from "./weather-labels";

const VALID_AXES = new Set(["truth", "relevance", "sentiment"] as const);
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

const ALL_EXPECTED_SLUGS: ReadonlyArray<string> = [
  ...TRUTH_SLUGS,
  ...RELEVANCE_SLUGS,
  ...SENTIMENT_SLUGS,
];

const JSON_KEYS = Object.keys(weatherLabelsJson);

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
    for (const [slug, entry] of Object.entries(weatherLabelsJson)) {
      expect(
        (entry as Record<string, unknown>)["axis"],
        `JSON entry "${slug}" is missing an axis field`,
      ).toBeDefined();
    }
  });

  it("every JSON entry specifies a label field", () => {
    for (const [slug, entry] of Object.entries(weatherLabelsJson)) {
      expect(
        (entry as Record<string, unknown>)["label"],
        `JSON entry "${slug}" is missing a label field`,
      ).toBeDefined();
    }
  });

  it("every JSON entry specifies a variant field", () => {
    for (const [slug, entry] of Object.entries(weatherLabelsJson)) {
      expect(
        (entry as Record<string, unknown>)["variant"],
        `JSON entry "${slug}" is missing a variant field`,
      ).toBeDefined();
    }
  });

  it("every JSON entry has a valid axis value", () => {
    for (const [slug, entry] of Object.entries(weatherLabelsJson)) {
      const axis = (entry as Record<string, unknown>)["axis"] as string;
      expect(
        VALID_AXES.has(axis as "truth" | "relevance" | "sentiment"),
        `JSON entry "${slug}" has invalid axis "${axis}" — must be one of: ${[...VALID_AXES].join(", ")}`,
      ).toBe(true);
    }
  });

  it("every JSON entry has a valid variant value that maps to a VARIANT_CLASSES key", () => {
    for (const [slug, entry] of Object.entries(weatherLabelsJson)) {
      const variant = (entry as Record<string, unknown>)["variant"] as string;
      expect(
        VALID_VARIANTS.has(variant),
        `JSON entry "${slug}" has invalid variant "${variant}" — must be one of: ${[...VALID_VARIANTS].join(", ")}`,
      ).toBe(true);
    }
  });
});
