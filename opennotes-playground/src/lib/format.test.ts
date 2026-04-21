import { describe, expect, it } from "vitest";
import { formatDate, getMetric, humanizeLabel } from "./format";

describe("humanizeLabel", () => {
  it("maps known Community Notes rating enum values", () => {
    expect(humanizeLabel("SOMEWHAT_HELPFUL")).toBe("Somewhat Helpful");
    expect(humanizeLabel("NOT_MISLEADING")).toBe("Not Misleading");
    expect(humanizeLabel("MISINFORMED_OR_POTENTIALLY_MISLEADING")).toBe("Potentially Misleading");
    expect(humanizeLabel("NEEDS_MORE_RATINGS")).toBe("Needs More Ratings");
  });

  it("maps known simulation status keywords", () => {
    expect(humanizeLabel("running")).toBe("Running");
    expect(humanizeLabel("completed")).toBe("Completed");
    expect(humanizeLabel("failed")).toBe("Failed");
  });

  it("falls back to title-casing snake_case for unknown keys", () => {
    expect(humanizeLabel("hello_world")).toBe("Hello World");
  });
});

describe("formatDate", () => {
  it("returns N/A for missing values", () => {
    expect(formatDate(null)).toBe("N/A");
    expect(formatDate(undefined)).toBe("N/A");
    expect(formatDate("")).toBe("N/A");
  });

  it("formats an ISO timestamp as a localized date string", () => {
    const formatted = formatDate("2026-04-21T10:30:00Z");
    expect(formatted).not.toBe("N/A");
    expect(formatted).toMatch(/2026/);
  });
});

describe("getMetric", () => {
  it("returns N/A for missing metrics bag", () => {
    expect(getMetric(null, "foo")).toBe("N/A");
    expect(getMetric(undefined, "foo")).toBe("N/A");
  });

  it("returns N/A when key is absent", () => {
    expect(getMetric({ bar: 1 }, "foo")).toBe("N/A");
  });

  it("returns N/A when value is null/undefined", () => {
    expect(getMetric({ foo: null }, "foo")).toBe("N/A");
    expect(getMetric({ foo: undefined }, "foo")).toBe("N/A");
  });

  it("stringifies numeric values", () => {
    expect(getMetric({ count: 42 }, "count")).toBe("42");
  });

  it("passes string values through", () => {
    expect(getMetric({ state: "ok" }, "state")).toBe("ok");
  });
});
