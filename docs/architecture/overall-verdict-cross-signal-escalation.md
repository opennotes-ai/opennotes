# Overall verdict: cross-signal synthesis

## Intent

The "Overall: OK." / "Overall: Flag!" line in `OverallRecommendationCard` (vibecheck-web) answers a single product question: **should a moderator (or someone in that role) intervene in this content?** It's a cost-benefit decision, not a tight summary of the safety agent:

- **Cost** of not intervening — the risk signals: safety agent verdict, conversation flashpoint matches, raw moderation findings, etc.
- **Benefit** of intervening — the utility signals: is the content worth the effort? Relevance, on-topic-ness, sourcing quality, engagement.

Pass means "the cost-benefit doesn't justify intervention". Flag means "it does".

The dimensions that contribute, grouped by side:

**Risk side**
1. **Safety recommendation** (high-level) — agent synthesis of moderation, web risk, image/video SafeSearch.
2. **Conversation flashpoint matches** (high-level) — tone dynamics from the "weather report".
3. **Raw analyzer findings** (low-level) — reserved slot for upcoming rules.

**Utility side**
1. **Weather report axes** (high-level) — `relevance`, `truth`, `sentiment`. Today only `truth × relevance` is consumed.
2. **Engagement / novelty** — not yet exposed in the payload; future signals.

This doc covers the cross-signal rules layered onto web-side derivation today. Eventually all of it moves server-side (see Migration).

## Rules in order

The rules below all run after the safety-recommendation base verdict (`decideFromSafety`). Each rule can promote `pass → flag`; none currently downgrade `flag → pass`.

### Rule 1 — Risk: mild safety + high flashpoint → Flag

When `OverallRecommendationCard` would derive `verdict: "pass"` and the safety level is exactly `mild`, promote to `verdict: "flag"` if any `tone_dynamics.flashpoint_matches` entry has `risk_level` in `{Heated, Hostile, Dangerous}`.

- Verdict label: reuse the existing `"Overall: Flag!"` copy. No third variant ("Overall: Caution!" etc) is introduced here.
- Reason text: `"Conversation flashpoint risk: <level>"` where `<level>` is the highest match risk level, priority `Dangerous > Hostile > Heated`.
- Explicit `overall` prop (manual override path) still wins over all derivation.

Concretely: the safety agent rated a civil personal-attack thread `mild` (no slurs/threats), while the conversation-flashpoint detector returned `Heated`. The overall card should not claim everything's fine.

### Rule 2 — Utility: misleading framing in on-topic discussion → Flag

When the running decision is `pass` and the weather report's truth axis is `misleading` AND the relevance axis is in `{insightful, on_topic}`, promote to `flag` with reason `"Misleading framing in on-topic discussion"`.

Rationale: a moderator should look at engaged, on-topic conversations whose framing is misleading, even when per-utterance safety stays mild. This is the simplest defensible cost-benefit rule we can build from current `weather_report` fields. Truth label `hearsay` is NOT included — too noisy without eval data.

Excluded relevance labels (`chatty`, `drifting`, `off_topic`) imply low intervention benefit — not worth a moderator's time even if misleading.

## Where computed

Web-side, in `OverallRecommendationCard.tsx`, via:

- `decideOverall(signals: OverallSignals): OverallDecision | null` — the composition function. Takes a typed bag of signals split into risk-side (`safetyRecommendation`, `flashpointMatches`), utility-side (`utility.weatherReport`), and a reserved lower-level slot, and runs each cross-signal rule in turn.
- `decideFromSafety(recommendation)` — the safety-recommendation base verdict.
- `escalateForFlashpoint(base, recommendation, matches)` — Rule 1, risk-side tone-dynamics escalation.
- `escalateForMisleadingOnTopic(base, weatherReport)` — Rule 2, utility-side misleading-on-topic escalation.

Rationale: the synthesis lives web-side only until the server-side overall-recommendation agent ships and owns the full cross-signal decision (safety + tone dynamics + page content + anything else that lands). Adding server schema fields for each rule before that agent ships would create churn for logic the agent will own anyway. Web-side keeps each rule small and easy to remove.

## Signal scope

Synthesis signals layered on today:

**Risk-side (Rule 1):**
- Source field: `tone_dynamics.flashpoint_matches: FlashpointMatch[]`
- Trigger: any entry where `risk_level in {Heated, Hostile, Dangerous}`
- Applies only when safety level is `mild`. `safe` is intentionally NOT escalated — a `safe` safety verdict is a strong signal and we don't want a flashpoint hit alone to override it.
- `Low Risk` and `Guarded` flashpoint matches never trigger escalation.

**Utility-side (Rule 2):**
- Source fields: `weather_report.truth.label`, `weather_report.relevance.label`
- Trigger: `truth.label == "misleading"` AND `relevance.label in {"insightful", "on_topic"}`
- Applies only when the running decision is `pass`; never downgrades `flag`.
- **Known sharp edge** (tracked in TASK-1618.14): the rule treats the winning `truth.label` as authoritative. A low-confidence `"misleading"` will still flag. **Gemini `logprob` values are intermittently broken and cannot be relied on**, so any mitigation must work without them — gate via the structural `alternatives` field (e.g., refuse to escalate when `alternatives[0].label` is `"factual_claims"` / `"sourced"`), multi-rule consensus, or eval-driven label-set tuning. If `logprob` happens to be present and trustworthy, it can serve as an optional tiebreaker, never a required input.

Engagement, novelty, and lower-level analyzer findings are not yet layered in web-side. They are deferred to the server-side overall agent below.

## Migration plan

When the server-side overall-recommendation agent ships, it owns the full synthesis — safety + tone dynamics + page content + anything else relevant — and emits a final verdict + reason. At that point:

1. Server emits the final overall verdict + reason on the payload.
2. `analyze.tsx` passes that through as `props.overall` (the existing manual-override path).
3. Drop `flashpointMatches` from `OverallRecommendationCardProps` and remove `escalateForFlashpoint`.
4. `decideOverall` / `decideFromSafety` either also go away, or stay only as a defensive fallback for legacy payloads.

The third-variant question (an explicit "Overall: Caution!" between OK and Flag) becomes a server-side decision at that point.

## Example payloads

(a) mild safety, no high flashpoint — stays OK:

```json
{
  "safety": {
    "recommendation": { "level": "mild", "rationale": "minor language", "top_signals": ["minor concern"] }
  },
  "tone_dynamics": {
    "flashpoint_matches": [
      { "risk_level": "Low Risk", "utterance_id": "u1", "derailment_score": 12, "reasoning": "calm exchange", "context_messages": 4, "scan_type": "conversation_flashpoint" }
    ]
  }
}
```

Renders: `Overall: OK.` with reason `minor concern`.

(b) mild safety + Heated flashpoint — escalates to Flag:

```json
{
  "safety": {
    "recommendation": { "level": "mild", "rationale": "no slurs or threats", "top_signals": ["civil tone"] }
  },
  "tone_dynamics": {
    "flashpoint_matches": [
      { "risk_level": "Heated", "utterance_id": "u3", "derailment_score": 62, "reasoning": "personal attack pattern", "context_messages": 4, "scan_type": "conversation_flashpoint" }
    ]
  }
}
```

Renders: `Overall: Flag!` with reason `Conversation flashpoint risk: Heated`.
