import { describe, expect, it } from "vitest";
import {
  formatWeatherBadgeClass,
  formatWeatherExpansion,
  formatWeatherLabel,
  formatWeatherVariant,
} from "./weather-labels";
import weatherLabelsJson from "./weather-labels.json";

describe("formatWeatherLabel — truth slugs (Title Case)", () => {
  it("returns 'Sourced' for sourced", () => {
    expect(formatWeatherLabel("sourced")).toBe("Sourced");
  });

  it("returns 'Factual Claims' for factual_claims", () => {
    expect(formatWeatherLabel("factual_claims")).toBe("Factual Claims");
  });

  it("returns 'First-Person' for first_person", () => {
    expect(formatWeatherLabel("first_person")).toBe("First-Person");
  });

  it("returns 'Second-Hand' for hearsay", () => {
    expect(formatWeatherLabel("hearsay")).toBe("Second-Hand");
  });

  it("returns 'Actively Misleading' for misleading", () => {
    expect(formatWeatherLabel("misleading")).toBe("Actively Misleading");
  });
});

describe("formatWeatherLabel — relevance slugs (Title Case)", () => {
  it("returns 'Insightful' for insightful", () => {
    expect(formatWeatherLabel("insightful")).toBe("Insightful");
  });

  it("returns 'On Topic' for on_topic", () => {
    expect(formatWeatherLabel("on_topic")).toBe("On Topic");
  });

  it("returns 'Chatty' for chatty", () => {
    expect(formatWeatherLabel("chatty")).toBe("Chatty");
  });

  it("returns 'Drifting' for drifting", () => {
    expect(formatWeatherLabel("drifting")).toBe("Drifting");
  });

  it("returns 'Off Topic' for off_topic", () => {
    expect(formatWeatherLabel("off_topic")).toBe("Off Topic");
  });
});

describe("formatWeatherLabel — sentiment palette slugs", () => {
  it("returns 'Supportive' for supportive", () => {
    expect(formatWeatherLabel("supportive")).toBe("Supportive");
  });

  it("returns 'Neutral' for neutral", () => {
    expect(formatWeatherLabel("neutral")).toBe("Neutral");
  });

  it("returns 'Critical' for critical", () => {
    expect(formatWeatherLabel("critical")).toBe("Critical");
  });

  it("returns 'Oppositional' for oppositional", () => {
    expect(formatWeatherLabel("oppositional")).toBe("Oppositional");
  });
});

describe("formatWeatherLabel — unknown slugs fall back to default title-caser", () => {
  it("title-cases a multi-word unknown slug (warmly skeptical)", () => {
    expect(formatWeatherLabel("warmly skeptical")).toBe("Warmly Skeptical");
  });

  it("title-cases an unknown underscore slug (engaged)", () => {
    expect(formatWeatherLabel("engaged")).toBe("Engaged");
  });
});

describe("formatWeatherVariant", () => {
  it("returns 'sky' for sourced", () => {
    expect(formatWeatherVariant("sourced")).toBe("sky");
  });

  it("returns 'indigo' for first_person", () => {
    expect(formatWeatherVariant("first_person")).toBe("indigo");
  });

  it("returns 'emerald' for insightful", () => {
    expect(formatWeatherVariant("insightful")).toBe("emerald");
  });

  it("returns 'slate' as default for unknown slugs", () => {
    expect(formatWeatherVariant("unknown_slug")).toBe("slate");
  });
});

describe("formatWeatherBadgeClass", () => {
  it("returns a class string containing text-sky-700 for sourced", () => {
    expect(formatWeatherBadgeClass("sourced")).toContain("text-sky-700");
  });

  it("returns a class string containing text-indigo-700 for first_person", () => {
    expect(formatWeatherBadgeClass("first_person")).toContain("text-indigo-700");
  });

  it("returns a class string containing text-emerald-700 for insightful", () => {
    expect(formatWeatherBadgeClass("insightful")).toContain("text-emerald-700");
  });

  it("returns a class string containing text-slate-700 for an unknown slug", () => {
    expect(formatWeatherBadgeClass("unknown_slug")).toContain("text-slate-700");
  });

  it("returns a string containing inline-flex and rounded-md for any slug", () => {
    const cls = formatWeatherBadgeClass("sourced");
    expect(cls).toContain("inline-flex");
    expect(cls).toContain("rounded-md");
  });
});

type WeatherLabelEntry = { axis: string; label: string; variant: string; expansion: string };

describe("weather-labels.json — expansion field contract", () => {
  it("every entry has a non-empty expansion string", () => {
    const entries = Object.entries(weatherLabelsJson) as [string, WeatherLabelEntry][];
    for (const [key, entry] of entries) {
      expect(entry.expansion, `entry "${key}" is missing expansion`).toBeDefined();
      expect(entry.expansion.length, `entry "${key}" has empty expansion`).toBeGreaterThan(0);
    }
  });
});

describe("formatWeatherExpansion — round-trip against JSON data", () => {
  it.each(Object.entries(weatherLabelsJson) as [string, WeatherLabelEntry][])(
    "exposes JSON expansion verbatim for %s",
    (key, entry) => {
      expect(
        formatWeatherExpansion(key as Parameters<typeof formatWeatherExpansion>[0])
      ).toBe(entry.expansion);
    }
  );
});

describe("formatWeatherExpansion — unknown labels", () => {
  it("returns null for a label not in the registry", () => {
    expect(formatWeatherExpansion("not_a_real_label" as Parameters<typeof formatWeatherExpansion>[0])).toBeNull();
  });
});
