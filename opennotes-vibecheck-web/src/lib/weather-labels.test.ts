import { describe, expect, it } from "vitest";
import {
  formatWeatherBadgeClass,
  formatWeatherExpansion,
  formatWeatherLabel,
  formatWeatherVariant,
  VARIANT_CLASSES,
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

describe("palette — no classic primary colors in VARIANT_CLASSES", () => {
  it("does not contain a 'blue' key in VARIANT_CLASSES", () => {
    expect(Object.keys(VARIANT_CLASSES)).not.toContain("blue");
  });

  it("does not contain a 'green' key in VARIANT_CLASSES", () => {
    expect(Object.keys(VARIANT_CLASSES)).not.toContain("green");
  });

  it("does not contain a 'rose' key in VARIANT_CLASSES", () => {
    expect(Object.keys(VARIANT_CLASSES)).not.toContain("rose");
  });

  it("does not produce a text-blue-700 class string from any variant", () => {
    for (const cls of Object.values(VARIANT_CLASSES)) {
      expect(cls).not.toContain("blue-700");
    }
  });

  it("does not produce a text-green-700 class string from any variant", () => {
    for (const cls of Object.values(VARIANT_CLASSES)) {
      expect(cls).not.toContain("green-700");
    }
  });

  it("does not produce a text-rose-700 class string from any variant", () => {
    for (const cls of Object.values(VARIANT_CLASSES)) {
      expect(cls).not.toContain("text-rose-700");
    }
  });

  it("contains 'lime' and 'fuchsia' keys in VARIANT_CLASSES", () => {
    expect(Object.keys(VARIANT_CLASSES)).toContain("lime");
    expect(Object.keys(VARIANT_CLASSES)).toContain("fuchsia");
  });
});

describe("palette — every JSON entry's variant is present in VARIANT_CLASSES", () => {
  it("each weather label variant key resolves to a class in VARIANT_CLASSES", () => {
    const entries = Object.entries(weatherLabelsJson) as [string, WeatherLabelEntry][];
    for (const [key, entry] of entries) {
      expect(
        Object.keys(VARIANT_CLASSES),
        `entry "${key}" has variant "${entry.variant}" which is not in VARIANT_CLASSES`,
      ).toContain(entry.variant);
    }
  });
});

describe("formatWeatherLabel — safety axis slugs", () => {
  it("returns 'Safe' for safe", () => {
    expect(formatWeatherLabel("safe")).toBe("Safe");
  });

  it("returns 'Mild' for mild", () => {
    expect(formatWeatherLabel("mild")).toBe("Mild");
  });

  it("returns 'Caution' for caution", () => {
    expect(formatWeatherLabel("caution")).toBe("Caution");
  });

  it("returns 'Unsafe' for unsafe", () => {
    expect(formatWeatherLabel("unsafe")).toBe("Unsafe");
  });
});

describe("formatWeatherVariant — safety axis slugs", () => {
  it("returns 'emerald-soft' for safe", () => {
    expect(formatWeatherVariant("safe")).toBe("emerald-soft");
  });

  it("returns 'yellow' for mild", () => {
    expect(formatWeatherVariant("mild")).toBe("yellow");
  });

  it("returns 'amber-strong' for caution", () => {
    expect(formatWeatherVariant("caution")).toBe("amber-strong");
  });

  it("returns 'rose-strong' for unsafe", () => {
    expect(formatWeatherVariant("unsafe")).toBe("rose-strong");
  });
});

describe("formatWeatherExpansion — safety axis slugs", () => {
  it("returns a non-null expansion string for safe", () => {
    const result = formatWeatherExpansion("safe");
    expect(result).not.toBeNull();
    expect(result!.length).toBeGreaterThan(0);
  });

  it("returns a non-null expansion string for mild", () => {
    const result = formatWeatherExpansion("mild");
    expect(result).not.toBeNull();
    expect(result!.length).toBeGreaterThan(0);
  });

  it("returns a non-null expansion string for caution", () => {
    const result = formatWeatherExpansion("caution");
    expect(result).not.toBeNull();
    expect(result!.length).toBeGreaterThan(0);
  });

  it("returns a non-null expansion string for unsafe", () => {
    const result = formatWeatherExpansion("unsafe");
    expect(result).not.toBeNull();
    expect(result!.length).toBeGreaterThan(0);
  });
});

describe("formatWeatherBadgeClass — safety axis slugs use traffic-light colors", () => {
  it("returns a class string containing text-emerald-800 for safe", () => {
    expect(formatWeatherBadgeClass("safe")).toContain("text-emerald-800");
  });

  it("returns a class string containing text-yellow-800 for mild", () => {
    expect(formatWeatherBadgeClass("mild")).toContain("text-yellow-800");
  });

  it("returns a class string containing text-amber-800 for caution", () => {
    expect(formatWeatherBadgeClass("caution")).toContain("text-amber-800");
  });

  it("returns a class string containing text-rose-50 for unsafe", () => {
    expect(formatWeatherBadgeClass("unsafe")).toContain("text-rose-50");
  });
});

describe("formatWeatherLabel — back-compat: existing axes unaffected by safety additions", () => {
  it("sourced still resolves to 'Sourced'", () => {
    expect(formatWeatherLabel("sourced")).toBe("Sourced");
  });

  it("on_topic still resolves to 'On Topic'", () => {
    expect(formatWeatherLabel("on_topic")).toBe("On Topic");
  });

  it("supportive still resolves to 'Supportive'", () => {
    expect(formatWeatherLabel("supportive")).toBe("Supportive");
  });
});

describe("VARIANT_CLASSES — safety traffic-light variants present", () => {
  it("contains 'emerald-soft' key", () => {
    expect(Object.keys(VARIANT_CLASSES)).toContain("emerald-soft");
  });

  it("contains 'yellow' key", () => {
    expect(Object.keys(VARIANT_CLASSES)).toContain("yellow");
  });

  it("contains 'amber-strong' key", () => {
    expect(Object.keys(VARIANT_CLASSES)).toContain("amber-strong");
  });

  it("contains 'rose-strong' key", () => {
    expect(Object.keys(VARIANT_CLASSES)).toContain("rose-strong");
  });
});
