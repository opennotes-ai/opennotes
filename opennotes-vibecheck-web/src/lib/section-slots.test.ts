import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  SECTION_SLUGS,
  asStrictSectionSlots,
  getSection,
  isSectionSlug,
} from "./section-slots";
import type { JobState, SectionSlot } from "./api-client.server";

const generatedTypesPath = resolve(
  process.cwd(),
  "src/lib/generated-types.ts",
);

function extractSectionSlugUnion(source: string): string[] {
  const match = source.match(/SectionSlug:\s*([^;]+);/);
  if (!match) {
    throw new Error("Could not locate SectionSlug definition in generated-types.ts");
  }
  const literals = match[1].match(/"([^"]+)"/g);
  if (!literals) {
    throw new Error("SectionSlug definition contained no string literals");
  }
  return literals.map((s) => s.slice(1, -1));
}

const doneSlot = (data: unknown = null): SectionSlot => ({
  state: "done",
  attempt_id: "00000000-0000-0000-0000-0000000000aa",
  data: data as SectionSlot["data"],
});

describe("SECTION_SLUGS", () => {
  it("matches the SectionSlug union in generated-types.ts (drift fails CI)", () => {
    const source = readFileSync(generatedTypesPath, "utf8");
    const generated = extractSectionSlugUnion(source);
    expect([...SECTION_SLUGS].sort()).toEqual([...generated].sort());
  });

  it("contains exactly twelve entries", () => {
    expect(SECTION_SLUGS).toHaveLength(12);
    expect(new Set(SECTION_SLUGS).size).toBe(12);
  });
});

describe("isSectionSlug", () => {
  it("accepts every literal in SECTION_SLUGS", () => {
    for (const slug of SECTION_SLUGS) {
      expect(isSectionSlug(slug)).toBe(true);
    }
  });

  it("rejects typos and non-strings", () => {
    expect(isSectionSlug("safetymoderation")).toBe(false);
    expect(isSectionSlug("safety_moderation")).toBe(false);
    expect(isSectionSlug("")).toBe(false);
    expect(isSectionSlug(undefined)).toBe(false);
    expect(isSectionSlug(null)).toBe(false);
    expect(isSectionSlug(42)).toBe(false);
  });
});

describe("getSection", () => {
  const state = {
    sections: {
      safety__moderation: doneSlot({ harmful_content_matches: [] }),
    } as unknown as JobState["sections"],
  } as JobState;

  it("returns the slot for a known slug", () => {
    const slot = getSection(state, "safety__moderation");
    expect(slot?.state).toBe("done");
  });

  it("returns undefined when the slot is missing", () => {
    const slot = getSection(state, "tone_dynamics__flashpoint");
    expect(slot).toBeUndefined();
  });

  it("returns undefined when state or sections is missing", () => {
    expect(getSection(null, "safety__moderation")).toBeUndefined();
    expect(getSection(undefined, "safety__moderation")).toBeUndefined();
    expect(getSection({} as JobState, "safety__moderation")).toBeUndefined();
  });
});

describe("asStrictSectionSlots", () => {
  it("filters keys to known slugs only", () => {
    const raw = {
      safety__moderation: doneSlot(),
      bogus_slug: doneSlot(),
    } as unknown as JobState["sections"];
    const strict = asStrictSectionSlots(raw);
    expect(Object.keys(strict)).toEqual(["safety__moderation"]);
  });

  it("returns an empty object for null/undefined", () => {
    expect(asStrictSectionSlots(null)).toEqual({});
    expect(asStrictSectionSlots(undefined)).toEqual({});
  });
});
