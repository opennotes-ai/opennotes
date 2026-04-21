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

export const TERM_DESCRIPTIONS: Record<string, string> = {
  // Consensus metrics
  mean_agreement: "Average agreement across all raters on each note (1.0 = unanimous, 0.0 = evenly split)",
  polarization_index: "How divided raters are across notes (high = deep disagreement, low = broad consensus)",
  notes_with_consensus: "Notes where raters show strong concord on helpfulness (not necessarily unanimous)",
  notes_with_disagreement: "Notes where raters significantly differ on helpfulness",
  total_notes_rated: "Total number of notes that have received at least one rating",
  // Note classifications
  NOT_MISLEADING: "Note argues the original content is accurate or not problematic",
  MISINFORMED_OR_POTENTIALLY_MISLEADING: "Note argues the original content contains inaccuracies or is misleading",
  // Note statuses
  CURRENTLY_RATED_HELPFUL: "Community consensus: this note is helpful",
  CURRENTLY_RATED_NOT_HELPFUL: "Community consensus: this note is not helpful",
  NEEDS_MORE_RATINGS: "Not enough ratings yet to determine helpfulness",
  // Helpfulness levels
  HELPFUL: "Rater found this note helpful",
  SOMEWHAT_HELPFUL: "Rater found this note partially helpful",
  NOT_HELPFUL: "Rater found this note not helpful",
};
