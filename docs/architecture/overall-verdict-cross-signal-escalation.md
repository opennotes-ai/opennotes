# Overall verdict: cross-signal synthesis

## Intent

The "Overall: OK." / "Overall: Flag!" line in `OverallRecommendationCard` (vibecheck-web) should be a synthesis of every primary analysis dimension on the page — not a restatement of the safety agent alone.

The dimensions that should contribute, in priority order:

1. **Safety recommendation** — moderation, web risk, image/video SafeSearch (the strongest single signal).
2. **Tone dynamics** ("weather report") — conversation flashpoint matches, derailment, hostility patterns that don't necessarily trip per-message moderation.
3. **Page content overall** — what the conversation/article is actually about; topical signals from claims/opinions/etc. that frame whether per-utterance findings are reasonable in context.

Today the card still derives its verdict mostly from the safety recommendation (`PASS_LEVELS = ["safe", "mild"]`), so any `mild` page renders "Overall: OK." even when the tone dynamics or page-level context disagree. That under-states what each agent already saw individually.

This doc covers the **first cross-signal rule** layered onto that derivation: a `mild` safety verdict should not stay `pass` when tone dynamics show a hostile conversation. More cross-signal rules belong here; eventually all of it moves server-side (see Migration).

## First rule: mild safety + high flashpoint → Flag

When `OverallRecommendationCard` would derive `verdict: "pass"` and the safety level is exactly `mild`, promote to `verdict: "flag"` if any `tone_dynamics.flashpoint_matches` entry has `risk_level` in `{Heated, Hostile, Dangerous}`.

- Verdict label: reuse the existing `"Overall: Flag!"` copy. No third variant ("Overall: Caution!" etc) is introduced here.
- Reason text: `"Conversation flashpoint risk: <level>"` where `<level>` is the highest match risk level, priority `Dangerous > Hostile > Heated`.
- Explicit `overall` prop (manual override path) still wins over all derivation.

Concretely: the safety agent rated a civil personal-attack thread `mild` (no slurs/threats), while the conversation-flashpoint detector returned `Heated`. The overall card should not claim everything's fine.

## Where computed

Web-side, in `OverallRecommendationCard.tsx`, via:

- `decideOverall(signals: OverallSignals): OverallDecision | null` — the composition function. Takes a typed bag of signals (higher-level: `safetyRecommendation`, `flashpointMatches`; lower-level slot reserved) and runs each cross-signal rule in turn.
- `decideFromSafety(recommendation)` — rule 1, the safety-recommendation base verdict.
- `escalateForFlashpoint(base, recommendation, matches)` — rule 2, the tone-dynamics escalation described above.

Rationale: the synthesis lives web-side only until the server-side overall-recommendation agent ships and owns the full cross-signal decision (safety + tone dynamics + page content + anything else that lands). Adding server schema fields for each rule before that agent ships would create churn for logic the agent will own anyway. Web-side keeps each rule small and easy to remove.

## Signal scope

The only synthesis signal layered on today:

- Source field: `tone_dynamics.flashpoint_matches: FlashpointMatch[]`
- Trigger: any entry where `risk_level in {Heated, Hostile, Dangerous}`
- Applies only when safety level is `mild`. `safe` is intentionally NOT escalated — a `safe` safety verdict is a strong signal and we don't want a flashpoint hit alone to override it. We can revisit if more cross-signal cases land.

`Low Risk` and `Guarded` flashpoint matches never trigger escalation.

Page-content / topical signals are not yet layered in web-side. They are deferred to the server-side overall agent below.

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
