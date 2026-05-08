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

describe("weather-labels.json — expansion field contract", () => {
  it("every entry has a non-empty expansion string", () => {
    const entries = Object.entries(weatherLabelsJson) as [string, { expansion?: string }][];
    for (const [key, entry] of entries) {
      expect(entry.expansion, `entry "${key}" is missing expansion`).toBeDefined();
      expect(entry.expansion!.length, `entry "${key}" has empty expansion`).toBeGreaterThan(0);
    }
  });
});

describe("formatWeatherExpansion — known labels", () => {
  it("returns the approved expansion for sourced", () => {
    expect(formatWeatherExpansion("sourced")).toBe(
      "Participants are pointing to outside sources to back up their claims."
    );
  });

  it("returns the approved expansion for factual_claims", () => {
    expect(formatWeatherExpansion("factual_claims")).toBe(
      "Participants are making claims that are theoretically possible to confirm."
    );
  });

  it("returns the approved expansion for first_person", () => {
    expect(formatWeatherExpansion("first_person")).toBe(
      "Participants are mostly speaking from direct, lived experience."
    );
  });

  it("returns the approved expansion for hearsay", () => {
    expect(formatWeatherExpansion("hearsay")).toBe(
      "Participants are mostly relaying what they heard from someone else."
    );
  });

  it("returns the approved expansion for misleading", () => {
    expect(formatWeatherExpansion("misleading")).toBe(
      "Participants are stating things in ways likely to mislead a reader."
    );
  });

  it("returns the approved expansion for insightful", () => {
    expect(formatWeatherExpansion("insightful")).toBe(
      "Participants are adding meaningful new perspective to the topic."
    );
  });

  it("returns the approved expansion for on_topic", () => {
    expect(formatWeatherExpansion("on_topic")).toBe(
      "The discussion stays close to the source's subject."
    );
  });

  it("returns the approved expansion for chatty", () => {
    expect(formatWeatherExpansion("chatty")).toBe(
      "The discussion is on-topic but mostly small talk."
    );
  });

  it("returns the approved expansion for drifting", () => {
    expect(formatWeatherExpansion("drifting")).toBe(
      "The discussion is wandering away from the source's subject."
    );
  });

  it("returns the approved expansion for off_topic", () => {
    expect(formatWeatherExpansion("off_topic")).toBe(
      "The discussion is no longer about the source's subject."
    );
  });

  it("returns the approved expansion for supportive", () => {
    expect(formatWeatherExpansion("supportive")).toBe(
      "Participants are mostly encouraging the topic, or each other."
    );
  });

  it("returns the approved expansion for neutral", () => {
    expect(formatWeatherExpansion("neutral")).toBe(
      "Participants are not taking a strong emotional stance."
    );
  });

  it("returns the approved expansion for critical", () => {
    expect(formatWeatherExpansion("critical")).toBe(
      "Participants are mostly criticizing a topic, or each other."
    );
  });

  it("returns the approved expansion for oppositional", () => {
    expect(formatWeatherExpansion("oppositional")).toBe(
      "Participants are taking adversarial stances toward the topic, or each other."
    );
  });
});

describe("formatWeatherExpansion — unknown labels", () => {
  it("returns null for a label not in the registry", () => {
    expect(formatWeatherExpansion("not_a_real_label" as Parameters<typeof formatWeatherExpansion>[0])).toBeNull();
  });
});
