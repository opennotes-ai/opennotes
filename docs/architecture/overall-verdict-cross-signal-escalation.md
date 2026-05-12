# Overall verdict: cross-signal escalation (mild safety + high flashpoint)

## Context

`OverallRecommendationCard` (vibecheck-web) derives a single-line "Overall: OK." / "Overall: Flag!" summary from the safety section of the analysis payload. The current rule treats `mild` as part of `PASS_LEVELS = ["safe", "mild"]`, so any conversation with a `mild` safety verdict shows "Overall: OK."

This produces a false negative on conversations whose language stays civil at the message level (no harassment / hate / threats triggering a stronger safety verdict) but whose flow is hostile or escalating, e.g. a civil personal-attack exchange. The safety agent rates it `mild`, while the conversation-flashpoint detector returns matches at `Heated` / `Hostile` / `Dangerous`. The overall card shouldn't claim everything's fine in that case.

## Decision

When `OverallRecommendationCard` would derive `verdict: "pass"` and the safety level is exactly `mild`, escalate to `verdict: "flag"` if any `tone_dynamics.flashpoint_matches` entry has `risk_level` in `{Heated, Hostile, Dangerous}`.

- Verdict label: reuse the existing `"Overall: Flag!"` copy. No third variant ("Overall: Caution!" etc) is introduced here.
- Reason text: `"Conversation flashpoint risk: <level>"` where `<level>` is the highest match risk level, priority `Dangerous > Hostile > Heated`.
- Explicit `overall` prop (manual override path) still wins over all derivation.

## Where computed

Web-side, in `OverallRecommendationCard` via an exported helper `escalateForFlashpoint(base, recommendation, flashpointMatches)`.

Rationale: the long-standing TODO at the top of `OverallRecommendationCard.tsx` plans to replace web derivation with a server-side overall-recommendation agent. Adding a server schema field for the cross-signal verdict before that agent lands would create churn (schema change, regen, redeploy) for logic the agent will own anyway. Doing it web-side keeps the change small and easy to remove.

## Override signals

The only escalation signal added in this change:

- Source field: `tone_dynamics.flashpoint_matches: FlashpointMatch[]`
- Trigger: any entry where `risk_level in {Heated, Hostile, Dangerous}`
- Applies only when safety level is `mild`. `safe` is intentionally NOT escalated — a `safe` safety verdict is a strong signal and we don't want a flashpoint hit alone to override it. We can revisit if more cross-signal cases land.

`Low Risk` and `Guarded` flashpoint matches never trigger escalation.

## Migration plan

When the server-side overall-recommendation agent ships:

1. Server emits the final overall verdict + reason on the payload.
2. `analyze.tsx` passes that through as `props.overall` (the existing manual-override path).
3. Drop `flashpointMatches` from `OverallRecommendationCardProps` and remove `escalateForFlashpoint`.
4. `deriveOverall` either also goes away, or stays only as a defensive fallback for legacy payloads.

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
