import { describe, expect, it } from "vitest";
import {
  categoryColor,
  categoryColorClasses,
  HARM_CONFIDENCE_THRESHOLD,
} from "./category-colors";

describe("categoryColor", () => {
  it("returns red for harm categories above the harm confidence threshold", () => {
    expect(categoryColor("violence", HARM_CONFIDENCE_THRESHOLD + 0.01)).toBe(
      "red",
    );
  });

  it("returns yellow for harm categories at or below the harm confidence threshold", () => {
    expect(categoryColor("violence", HARM_CONFIDENCE_THRESHOLD)).toBe(
      "yellow",
    );
  });

  it("returns gray for sensitive categories regardless of confidence", () => {
    expect(categoryColor("Finance", 0.98)).toBe("gray");
  });

  it("returns yellow for unknown future categories", () => {
    expect(categoryColor("novelty/future", 0.99)).toBe("yellow");
  });

  it("recognizes OpenAI subcategory paths by their root category", () => {
    expect(categoryColor("sexual/minors", 0.99)).toBe("red");
  });

  it("recognizes GCP Natural Language categories case-insensitively", () => {
    expect(categoryColor("Harm & Tragedy", 0.9)).toBe("red");
  });

  it("treats missing confidence as high confidence for bool-only harm flags", () => {
    expect(categoryColor("harassment", undefined)).toBe("red");
  });
});

describe("categoryColorClasses", () => {
  it("returns classes for the red variant", () => {
    expect(categoryColorClasses("red")).toBe(
      "bg-destructive/10 text-destructive",
    );
  });

  it("returns classes for the yellow variant", () => {
    expect(categoryColorClasses("yellow")).toBe(
      "bg-amber-500/10 text-amber-600 dark:text-amber-500",
    );
  });

  it("returns classes for the gray variant", () => {
    expect(categoryColorClasses("gray")).toBe(
      "bg-muted text-muted-foreground",
    );
  });
});
