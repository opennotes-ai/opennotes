# ADR: Gemini 3 vs Flash-Lite for scrape quality gating (TASK-1488.23)

Date: 2026-04-29
Status: Proposed
Task: TASK-1488.23

## Context

`opennotes-vibecheck-server` currently uses a deterministic, fixed-string heuristic classifier (`classify_scrape()`) to decide the `/scrape -> /interact` ladder behavior:

- `classify_scrape()` labels each scrape as `AUTH_WALL`, `INTERSTITIAL`, `LEGITIMATELY_EMPTY`, or `OK`.
- `/scrape` (`Tier 1`) and `/interact` (`Tier 2`) flow dispatch depends on this classification in `src/jobs/orchestrator.py`.
- `AUTH_WALL` and `LEGITIMATELY_EMPTY` are terminal; only `INTERSTITIAL` can be escalated to `/interact`.
- The page content and metadata are attacker-controlled, so the classifier currently avoids regex and uses fixed-string checks and narrowly scoped parsing to reduce parser/regex risk.

Current classification safety properties:

- deterministic behavior for deterministic retries;
- no network call, no prompt injection surface, no JSON parsing from untrusted LLM output;
- low latency relative to extraction.

This ADR is to evaluate adding an LLM classifier in front of or instead of this scraper heuristic, with **Gemini 3 Flash as the default candidate for any future LLM classifier/confirmer path** and a Flash-Lite challenger path only after controlled validation. This ADR defines a **future eval/shadow plan only**.

No TASK-1488.23 testing has shown that Flash-Lite materially outperforms the current heuristic under this task’s scope; no runtime enforcement is being made in this ADR.

## Official model facts (as of 2026-04-29)

- Gemini 3 Flash model docs: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-flash
- Gemini 3.1 Flash-Lite model docs: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-1-flash-lite
- Vertex AI pricing docs: https://cloud.google.com/vertex-ai/generative-ai/pricing
- Gemini Flex PayGo docs: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/flex-paygo
- As stated in the task brief and cited by current official docs snapshots on 2026-04-29:
  - Gemini 3 Flash:
    - model ID: `gemini-3-flash-preview`
    - launch stage: Public preview
    - release date: 2025-12-17
    - last updated: 2026-04-23 UTC
    - pricing:
      - Standard Runtime (PayGo): input `text/image/video $0.50 / 1M`, audio `$1.00 / 1M`, text output `$3.00 / 1M`
      - Flex/Batch (Flex PayGo): input `text/image/video $0.25 / 1M`, audio `$0.50 / 1M`, output `$1.50 / 1M`
  - Gemini 3.1 Flash-Lite:
    - model ID: `gemini-3.1-flash-lite-preview`
    - launch stage: Public preview
    - release date: 2026-03-03
    - last updated: 2026-04-23 UTC
    - pricing:
      - Standard Runtime (PayGo): input `text/image/video $0.25 / 1M`, audio `$0.50 / 1M`, text output `$1.50 / 1M`
      - Flex/Batch (Flex PayGo): input `text/image/video $0.13 / 1M`, audio `$0.25 / 1M`, output `$0.75 / 1M`

## Option 1 — keep current deterministic heuristic only

### Description

Keep `classify_scrape()` as-is and do not call Gemini in the scrape ladder path.

### Cost

No direct model cost.

### Latency and reliability

- Lowest added latency (zero external round trip).
- Existing reliability remains stable and deterministic.
- No additional preview-model availability/SDK risks.

### Security and jailbreak posture

- No LLM prompt attack surface.
- No remote parsing/untrusted text generation required in this decision point.
- Continues to classify on attacker-provided html/markdown using fixed-string and parser-path checks.

### Failure behavior

- Existing failure behavior preserved exactly.
- No fallback path needed because there is no new dependency.
- Deterministic classification preserves replayability on retries.

### Operational and evaluation impact

- Zero additional telemetry changes required.
- Minimal observability changes beyond existing tier transition metrics in orchestration spans.

## Option 2 — add Gemini 3 Flash as the default confirmer for ambiguous cases

### Description

Run the existing heuristic first; only in ambiguous cases (likely `INTERSTITIAL` candidates or low-confidence markers) call Gemini in a verifier role to decide whether to escalate.
The default candidate for this option is Gemini 3 Flash.
Gemini 3.1 Flash-Lite remains a challenger, only for follow-up downgrade consideration if cost and safety criteria are met.

#### Decision matrix (proposed; current recommended)

- Runtime recommendation remains heuristic-only today; Gemini is shadow-only until explicit enforcement is approved.
- In shadow mode, Gemini output is logged and compared against the existing heuristic result.
- To preserve the ToS/security boundary, valid-output override rules are:
  - `AUTH_WALL` and `LEGITIMATELY_EMPTY` are terminal and **never** promotable to `/interact` without a separate, explicitly approved follow-up decision.
  - Gemini can only target ambiguous/interstitial buckets for any future enforcement.

| Heuristic outcome | Gemini output | Shadow behavior | Enforced confirmer behavior (if approved separately) |
| --- | --- | --- | --- |
| `AUTH_WALL` | `AUTH_WALL` | log `match` | terminal `AUTH_WALL` |
| `AUTH_WALL` | `INTERSTITIAL` / `OK` / `LEGITIMATELY_EMPTY` | log override attempt (terminal) | terminal `AUTH_WALL` |
| `LEGITIMATELY_EMPTY` | `LEGITIMATELY_EMPTY` | log `match` | terminal `LEGITIMATELY_EMPTY` |
| `LEGITIMATELY_EMPTY` | `AUTH_WALL` / `INTERSTITIAL` / `OK` | log override attempt (terminal) | terminal `LEGITIMATELY_EMPTY` |
| `INTERSTITIAL` (ambiguous bucket) | `INTERSTITIAL` | log confirm escalate | escalate to `/interact` |
| `INTERSTITIAL` (ambiguous bucket) | `AUTH_WALL` | log demotion to `AUTH_WALL` | terminal `AUTH_WALL` |
| `INTERSTITIAL` (ambiguous bucket) | `LEGITIMATELY_EMPTY` | log demotion to `LEGITIMATELY_EMPTY` | terminal `LEGITIMATELY_EMPTY` |
| `INTERSTITIAL` (ambiguous bucket) | `OK` | log confirm-pass | conservative hold: no escalation without separate review |

### Cost (assumptions)

No grounding for classifier calls.

For runtime decisions, prefer Gemini 3 Standard PayGo as the default and compare Flash-Lite only as a challenger.

`cost = (input_tokens / 1_000_000 * input_rate) + (output_tokens / 1_000_000 * output_rate)`

1. 4K input + 100 output
   - Gemini 3 Standard: `(4,000 / 1,000,000 * $0.50) + (100 / 1,000,000 * $3.00) = $0.002000 + $0.000300 = $0.00230` per call
2. 20K input + 100 output
   - Gemini 3 Standard: `(20,000 / 1,000,000 * $0.50) + (100 / 1,000,000 * $3.00) = $0.010000 + $0.000300 = $0.01030` per call
   - Standard lower-bound estimate: ~1 input/output round trip per selected ambiguous case.

Flex/Batch is separated from runtime-latency-sensitive paths:
- Flex/Batch is intended for non-critical, latency-tolerant and potentially throttled workloads, matching Vertex AI Flex PayGo guidance.
- Use Flex/Batch only for shadow/eval backfill or overnight calibration jobs, not for synchronous `/scrape -> /interact` control.

Flash-Lite challenger baseline for cost comparison:
- 4K input + 100 output: `~$0.00115` per call (half the Gemini 3 Standard text/input rate).
- 20K input + 100 output: `~$0.00515` per call.
  - This Challenger path is only acceptable if quality/security gates pass and head-to-head tests show no material safety regression.

Illustrative Flex/Batch examples for same payloads:
- 4K input + 100 output:
  - Gemini 3 Flex/Batch: `(4,000 / 1,000,000 * $0.25) + (100 / 1,000,000 * $1.50) = $0.001000 + $0.000150 = $0.00115`
  - Flash-Lite Flex/Batch: `(4,000 / 1,000,000 * $0.13) + (100 / 1,000,000 * $0.75) = $0.000595`
- 20K input + 100 output:
  - Gemini 3 Flex/Batch: `(20,000 / 1,000,000 * $0.25) + (100 / 1,000,000 * $1.50) = $0.005000 + $0.000150 = $0.00515`
  - Flash-Lite Flex/Batch: `(20,000 / 1,000,000 * $0.13) + (100 / 1,000,000 * $0.75) = $0.002675`

### Latency and reliability

Adds one network call only for selected cases; end-to-end scrape latency rises for those pages.
`interact` already adds latency/complexity in one branch, so this is incremental and bounded by ambiguity rate.
Introduce model timeouts/guardrails as proposals (not measured values; no baseline observations yet):

- Hard per-call timeout cap: 1.5s at the request layer.
- Retry policy: no automatic retry in the classifier path (single-shot only), because retries can amplify latency and cost on flaky upstreams.
- Proposed added latency budgets for confirmer path:
  - target `p95` add-on ≤ 700ms,
  - target `p99` add-on ≤ 1,400ms,
  - `error_or_timeout_rate` target ≤ 1.5% during shadow.
- Proposed shadow-mode rollout gate:
  - phase 1 run for at least 7 days with ≥ 10,000 confirmer opportunities and ≥ 1,000 per top host before promotion discussion.
  - if either budget is breached (p99 add-on > 1,500ms, or timeout/error > 2%), disable confirmer by feature flag.
- Introduces preview model risk and SDK/API failure surface; must enforce hard timeout and fallback.

### Security and jailbreak posture

- Attacker-controlled page text/HTML enters prompt context, creating an indirect prompt-injection risk.
- Must treat model output as untrusted:
  - strict schema/enum validation,
  - deny-list disallowed free-form values,
  - reject invalid outputs,
  - default to current deterministic outcome on parse/timeout/error.
- Keep a hard fail-closed policy for parser failures.
- Use very small, narrow prompts and explicit constraints.

### Failure behavior

- On timeout/error/parsing/invalid structured output, preserve existing deterministic behavior (no escalation or fallback to raw text).
- Do not expose raw Gemini text to users.
- Preserve current terminal vs escalate behavior as source of truth.

### Operational and evaluation impact

- Requires telemetry for confirmer path:
  - request count, fallback count, timeout/error/parse-fail count,
  - per-host confirmer invocation and disagreement rate,
  - added latency by stage.
- Evaluate by category (e.g., cloudflare-like interstitial, login-wall pages, empty/deleted, normal OK pages, JS-rendered edge pages, and known mixed-content pages).
- Run in shadow mode first by comparing confirm output with existing classifier outcome and logging a `decision_match` signal.

## Option 3 — replace heuristic classifier entirely with Gemini 3 Flash

### Description

Use Gemini 3 output as the single decision source for scrape ladder dispatch.
Evaluate Gemini 3.1 Flash-Lite as a cost-optimized challenger only if it meets all quality/security gates.

### Cost

Every scrape attempt can hit Gemini, so costs scale with all traffic:
- at 4K input + 100 output and 1M calls/month:
  - Gemini 3 Standard: ~`$2,300/month` runtime.
- at 20K input + 100 output and 1M calls/month:
  - Gemini 3 Standard: ~`$10,300/month` runtime.
- Real-world totals likely higher due to retries and malformed payload retries.

Flash-Lite evaluated alternative (non-default):
- 4K input + 100 output and 1M calls: ~`$1,150/month` (same formula as Flash-Lite Standard).
- 20K input + 100 output and 1M calls: ~`$5,150/month`.

For Flex/Batch-only workflows (non-realtime eval or backfill):
- Gemini 3: `~$1,150/month` at 4K and `~$5,150/month` at 20K (1M calls/month) in Flex/Batch.
- Flash-Lite: `~$595/month` at 4K and `~$2,675/month` at 20K (1M calls/month) in Flex/Batch.

### Latency and reliability

- Adds external dependency to all `/scrape` decisions, increasing baseline pipeline latency.
- Preview API availability/stability becomes a platform dependency for every scrape path.
- Harder to provide strict SLOs unless extensive caching and async/timeout controls are added.
- Proposed baseline budgets (not measured):
  - hard request timeout cap: 1.5s,
  - no automatic model retries in the primary path,
  - target added `p95` latency ≤ 900ms and `p99` ≤ 1,900ms versus current heuristic-only path.

### Security and jailbreak posture

- Highest prompt-security risk because every decision depends on model interpretation of hostile text/HTML.
- Same output-schema/validation and fail-closed behavior is mandatory, but there is no deterministic fallback for all cases unless a second classifier is kept as a backup.
- More extensive prompt-hardening and poisoning tests required.

### Failure behavior

- Must define deterministic fallback behavior for LLM failure states:
  - timeout/error/degradation.
- If fallback is `heuristic`, runtime effectively becomes Option 2 in failure.
- If fallback is `default` (e.g., terminal or escalate), either choice changes system behavior materially.

### Operational and evaluation impact

- Major instrumentation required before rollout:
  - full calibration by host, by content class, by locale;
  - false-positive and false-negative tracking against labeled gold set;
  - cost/latency per site and per page class;
  - drift and prompt drift monitors.
- Must add strict output validation and a shadow run at minimum before enforcement.

## Cross-cutting requirements if Gemini is introduced

- No grounding for scrape classifier calls.
- Strict structured output only (enum-like schema).
- Deterministic fallback on timeout/error/invalid output; never show user-facing model text.
- Keep current behavior as the safe base unless proven improvement is quantified.
- Per-host and per-class error budgets before any hard switch.
- One-time shadow deployment with operator review first.

## Monitoring/Evals Plan

### Concrete eval-set plan (proposed, not implemented yet)

Use a human-labeled gold set for shadow comparisons before any runtime switch.

- Total target sample size: **2,000 pages**.
- Labeling rule: 3 reviewers + majority vote, with adjudication on ties.
- Required schema labels: `AUTH_WALL`, `INTERSTITIAL`, `LEGITIMATELY_EMPTY`, `OK`.

| Fixture stratum | Target samples | Example fixture types | Expected schema label |
| --- | ---: | --- | --- |
| `AUTH_WALL` | 300 | login forms with password input, explicit `/login`/`/signin` form actions, 401/403 pages that clearly indicate credential gating | `AUTH_WALL` |
| `INTERSTITIAL` | 350 | Cloudflare-style challenge pages, JS-required/no-js fallbacks, interaction challenge pages with browser challenge text/class names | `INTERSTITIAL` |
| `LEGITIMATELY_EMPTY` | 300 | 404/410 pages, deleted/content removed notices, empty scrape bundle bodies with no meaningful content | `LEGITIMATELY_EMPTY` |
| `OK` | 800 | stable content pages with clear extractable markdown body and low ambiguity markers | `OK` |
| `LOGIN_REDIRECT_MIXED` | 150 | auth redirect flows from public landing → login, mixed with page content around the redirect | `AUTH_WALL` if access is blocked, else `INTERSTITIAL` if clear JS challenge, never `OK` |
| `SHORT_LOW_CONTENT` | 100 | very short pages around threshold lengths, boilerplate-heavy pages, low-token but non-empty payloads | `LEGITIMATELY_EMPTY` unless clear evidence supports `INTERSTITIAL`/`AUTH_WALL` |

- Per-class minimum acceptance thresholds for the shadow confirmer:
  - Macro `F1 >= 0.88` across all classes.
  - Per-class precision/recall:
    - `AUTH_WALL`: precision ≥ 0.97, recall ≥ 0.98
    - `LEGITIMATELY_EMPTY`: precision ≥ 0.96, recall ≥ 0.95
    - `INTERSTITIAL`: precision ≥ 0.92, recall ≥ 0.90
    - `OK`: precision ≥ 0.93, recall ≥ 0.90
  - These four-class threshold gates apply only to schema outputs (`AUTH_WALL`, `INTERSTITIAL`, `LEGITIMATELY_EMPTY`, `OK`).
  - Added latency budgets:
    - `p95` ≤ 700ms, `p99` ≤ 1,400ms (same guardrails as above).
  - Disagreement rate:
    - ≤ 12% on full shadow set and ≤ 18% on `LOGIN_REDIRECT_MIXED`.
  - Confirmer call quality:
    - parse/schema reject rate ≤ 1.0%,
    - error + timeout + retry-fallback rate ≤ 2.0%.
- Stratum-level acceptance checks (in addition to class-level metrics):
  - `LOGIN_REDIRECT_MIXED`: disagreement ≤ 18%.
  - `SHORT_LOW_CONTENT`: disagreement ≤ 20%.
- Head-to-head flash-vs-flash-lite precondition for any future downgrade to Flash-Lite:
  - Run the same 2,000-page labeled set through both models in parallel.
  - Require paired statistical comparison on safety-critical classes:
    - `AUTH_WALL`: Flash-Lite precision/recall delta vs Gemini 3 `>= -0.005` (non-inferiority margin 0.5pp), with paired 95% CI lower bound `>= -0.005`.
    - `LEGITIMATELY_EMPTY`: Flash-Lite precision/recall delta vs Gemini 3 `>= -0.005`, with paired 95% CI lower bound `>= -0.005`.
  - Require overall quality non-inferiority:
    - Flash-Lite macro `F1` delta vs Gemini 3 `>= -0.01` (non-inferiority margin 1pp), or better.
  - Only if this passes and latency/cost improves materially without worse safety gates can Flash-Lite be considered for downgrade from Flash.

### Proposed instrumentation for all options with Gemini

- Metrics to add:
  - `false_positive` / `false_negative` by class versus human-labeled set,
  - agreement/disagreement against current heuristic when shadowing,
  - timeout/error/parser-fail/error schema reject rates,
  - cost/latency per request and p95/p99,
  - per-host breakout (especially top 50 scrape hosts).
- Evaluation mode:
 1. shadow only for 1–2 weeks,
 2. no runtime branching change; log only,
 3. include parallel scoring for Gemini 3 and Flash-Lite on the same traffic sample.
 4. gate on defined disagreement, guardrails, and non-inferiority thresholds above.

## Recommendation

For this task, recommend **keep the deterministic heuristic classifier as current runtime behavior**.
When moving beyond this ADR’s shadow/eval scope, adopt Gemini 3 Flash as the default model for any future classifier confirmer/enforcer path.
Treat Gemini 3.1 Flash-Lite only as a challenger/cost-optimized fallback path, and only approve downgrade if it is materially better on latency/cost, passes all safety gates, and passes the non-inferiority criteria above.

This keeps `/scrape -> /interact` control flow stable, avoids immediate dependency on a preview LLM for gating logic, and prevents behavior drift on attacker-controlled inputs while preserving current safety guarantees.
