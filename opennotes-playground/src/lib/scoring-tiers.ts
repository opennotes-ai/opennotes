export const TIER_DESCRIPTIONS: Record<string, { label: string; description: string; helpfulnessNote: string }> = {
  MINIMAL: {
    label: "Minimal",
    description: "0\u2013200 notes. Simple Bayesian averaging.",
    helpfulnessNote: "Score is a rough estimate based on limited data.",
  },
  minimal: {
    label: "Minimal",
    description: "0\u2013200 notes. Simple Bayesian averaging.",
    helpfulnessNote: "Score is a rough estimate based on limited data.",
  },
  LIMITED: {
    label: "Limited",
    description: "200\u20131,000 notes. Matrix factorization (MFCore).",
    helpfulnessNote: "Score uses basic matrix factorization but may be unreliable.",
  },
  limited: {
    label: "Limited",
    description: "200\u20131,000 notes. Matrix factorization (MFCore).",
    helpfulnessNote: "Score uses basic matrix factorization but may be unreliable.",
  },
  BASIC: {
    label: "Basic",
    description: "1,000\u20135,000 notes. Full MFCore scorer.",
    helpfulnessNote: "Score is reasonably reliable via MFCore.",
  },
  basic: {
    label: "Basic",
    description: "1,000\u20135,000 notes. Full MFCore scorer.",
    helpfulnessNote: "Score is reasonably reliable via MFCore.",
  },
  INTERMEDIATE: {
    label: "Intermediate",
    description: "5,000\u201310,000 notes. MFCore + Expansion scorers.",
    helpfulnessNote: "Score is reliable, combining core and expansion models.",
  },
  intermediate: {
    label: "Intermediate",
    description: "5,000\u201310,000 notes. MFCore + Expansion scorers.",
    helpfulnessNote: "Score is reliable, combining core and expansion models.",
  },
  ADVANCED: {
    label: "Advanced",
    description: "10,000\u201350,000 notes. Full pipeline with group-aware scoring.",
    helpfulnessNote: "High-confidence score using full scoring pipeline.",
  },
  advanced: {
    label: "Advanced",
    description: "10,000\u201350,000 notes. Full pipeline with group-aware scoring.",
    helpfulnessNote: "High-confidence score using full scoring pipeline.",
  },
  FULL: {
    label: "Full",
    description: "50,000+ notes. Complete pipeline with clustering.",
    helpfulnessNote: "Highest-confidence score with all scorer types.",
  },
  full: {
    label: "Full",
    description: "50,000+ notes. Complete pipeline with clustering.",
    helpfulnessNote: "Highest-confidence score with all scorer types.",
  },
};

export function getHelpfulnessTooltip(score: number | null | undefined, tier: string): string {
  if (score == null) {
    return "Helpfulness: N/A";
  }
  const tierInfo = TIER_DESCRIPTIONS[tier];
  const status = score >= 0.5 ? "Helpful" : "Not Helpful";
  const base = `Helpfulness: ${score.toFixed(2)} (${status})`;
  return tierInfo ? `${base}. ${tierInfo.helpfulnessNote}` : base;
}
