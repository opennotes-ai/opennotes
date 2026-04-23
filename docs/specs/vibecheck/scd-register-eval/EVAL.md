# TASK-1471.23.08 — SCD Conversational-Register Before/After Eval

**Date:** 2026-04-22
**Branch:** tasks-1471.23 (HEAD `d4989a5a`, parent `90e2185d`)
**Method:** Hybrid (Option B). Three hand-crafted transcripts run through a real
Vertex AI Gemini 3.1 Pro Preview call via the production `build_agent`, with
both the OLD prompt (Cornell ConvoKit verbatim, recovered from the parent
commit) and the NEW prompt (current `scd_prompt.txt` on this branch). Resulting
`SCDReport` JSON for each pair is saved alongside this doc; the rendered text
of the new `ScdReport.tsx` for each NEW payload is captured via Vitest +
`@solidjs/testing-library` (jsdom). Pixel screenshots were skipped — the
qualitative read here is about copy register, which renders identically as
text. Layout/typography is covered by component tests already on this branch.

## Inputs

- Transcripts: see `transcripts.md` in this directory.
  - **Transcript 1 — heated multi-speaker** (9 utterances, 4 speakers,
    Reddit r/relationships flavor with escalation + a mediator).
  - **Transcript 2 — measured comment section** (6 utterances, 3 speakers,
    Hacker News flavor, polite technical disagreement).
  - **Transcript 3 — single-author monologue** (1 utterance, 1 author,
    blog-style). Triggers the `analyze_scd` short-circuit
    (`insufficient_conversation=True`); no LLM call fires for either prompt,
    both produce the same fixed insufficient report.
- Eval script: `opennotes-vibecheck-server/scripts/eval_scd_register.py`.
- Render dump: `opennotes-vibecheck-web/tests/eval/scd-render-dump.eval.test.tsx`.

### How the OLD vs NEW calls were shaped

The OLD prompt embeds a `{formatted_object}` placeholder mid-prompt and ends
with `Trajectory Summary:` expecting the model to continue. To match that
shape, the eval script interpolates the formatted transcript into the system
prompt and sends a minimal user message ("Produce the trajectory summary as
instructed above.") so Vertex Gemini accepts the request. The NEW prompt is
used as-is as a system prompt and the formatted transcript is sent as the user
message, exactly mirroring `analyze_scd`. Both calls use the same model
(`gemini-3.1-pro-preview`), same `output_type=SCDReport`, same
`build_agent(...)` factory.

## Transcript 1 — heated multi-speaker

### OLD prompt — `narrative`

> The conversation begins with the original poster seeking validation for
> their feelings of shock and distress regarding a major life change. A
> respondent immediately offers firm validation, but a second respondent
> challenges this, suggesting a more empathetic and investigative approach.
> This sparks a brief, slightly combative debate between the two respondents
> over conversational burden and accountability. As the original poster
> provides clarifying details that emphasize their feelings of betrayal, a
> fourth speaker jumps in to mediate. The mediator points out that the debate
> is distracting from the original poster's immediate need for emotional
> support. This intervention acts as a turning point; both debaters quickly
> concede their arguments, apologize for their previous intensity, and
> collaboratively shift their focus to offering unified sympathy and
> supportive advice to the original poster.

### NEW prompt — `narrative`

> It begins with a raw, vulnerable request for a reality check. One person
> jumps in to offer firm validation, but someone else immediately pushes back
> to argue for more nuance. This kicks off a brisk, mildly combative
> side-debate between the two commenters. The original poster briefly
> surfaces to add context, but the energy doesn't really shift until a new
> voice drops in to play referee. This newcomer gently calls out the
> bickering and redirects everyone's focus back to the original poster's
> emotional state. The intervention works perfectly: both debaters instantly
> drop their defensive postures, concede the point, and unite to close the
> thread out with warm, aligned support.

### NEW prompt — `speaker_arcs` (note + range)

- **op_throwaway** (turns 1-6): "Reaches out in a state of shock looking for
  grounding, and steps in just once more to clarify the situation while
  letting others hash it out."
- **alex_91** (turns 2-8): "Starts off deeply validating but highly
  definitive, gets into a defensive scrap, and then gracefully takes the L
  and softens their stance."
- **brenna_h** (turns 3-9): "Enters pushing for nuance and gets defensive
  when challenged, but ultimately lets the argument go to show up for the
  original poster."
- **cyrus_t** (turns 7-7): "Acts as the essential circuit breaker, dropping
  in just once to reframe the entire vibe and successfully de-escalate the
  room."

### NEW prompt — `tone_labels`

`vulnerable`, `scrappy`, `reconciliatory`, `supportive`

### Sidebar render (NEW shape via `ScdReport.tsx`)

See `transcript-1-heated/rendered.md`. Narrative and arc notes appear as
written above; tone labels render as chip pills; `cyrus_t`'s single-turn arc
correctly renders as `turns 7-7`.

## Transcript 2 — measured comment section

### OLD prompt — `narrative`

> The conversation starts with an open, inquisitive prompt from the first
> speaker seeking a decision-making heuristic. A second speaker offers a
> concrete, experience-based rule, which prompts a third speaker to politely
> push back and reframe the underlying criteria. Instead of becoming
> defensive, the second speaker readily concedes, acknowledging the validity
> of the reframing while explaining their original reasoning. The first
> speaker then re-enters the discussion to synthesize both perspectives,
> proposing a unified practical rule. Finally, the third speaker validates
> this synthesized conclusion. Overall, the exchange is highly collaborative
> and analytical. The participants effectively use polite disagreement,
> concession, and synthesis to collectively refine their understanding
> without any escalation or hostility.

### NEW prompt — `narrative`

> The exchange kicks off with a direct question seeking advice on a common
> trade-off. Someone quickly jumps in with a specific, experience-based
> answer to get things started. Almost immediately, a third person enters to
> gently challenge the premise of that answer, suggesting a different
> underlying way to look at the problem. Instead of getting defensive, the
> second person readily concedes, validating the new perspective while
> explaining their original reasoning. The initial questioner then steps
> back in to play synthesizer, blending both viewpoints into a practical
> rule of thumb. The conversation wraps up smoothly with the third person
> validating this new synthesis. Overall, it is a brisk, highly
> collaborative thread where participants actively listen, gracefully accept
> pushback, and work together to arrive at a shared conclusion.

### NEW prompt — `speaker_arcs`

- **dgreene** (turns 1-5): "Opens the floor with a genuine question, absorbs
  the resulting back-and-forth, and returns to synthesize a practical middle
  ground."
- **emoss** (turns 2-4): "Offers a firm, experience-based answer initially,
  but gracefully accepts pushback and adapts their stance."
- **fperez** (turns 3-6): "Steps in to gently reframe the core metric being
  discussed and finishes by validating the group's final consensus."

### NEW prompt — `tone_labels`

`collaborative`, `constructive`, `civil`, `pragmatic`, `warm`

### Sidebar render (NEW shape)

See `transcript-2-measured/rendered.md`.

### Note on `per_speaker_notes`

The NEW response left `per_speaker_notes` empty (`{}`), even though the prompt
still asks for it as a back-compat duplicate of `speaker_arcs[].note`. The OLD
response populated it. This is a real but minor regression: existing consumers
that haven't migrated to `speaker_arcs` will see no per-speaker text for this
transcript. Frontend consumers on this branch already read `speaker_arcs` so
the rendered sidebar is unaffected. Worth flagging as a follow-up: either
tighten the prompt (add an explicit "REQUIRED — populate even though it
duplicates") or remove the legacy field once all consumers are migrated.

## Transcript 3 — single-author monologue

`analyze_scd` short-circuits when `len(utterances) < 2` or
`distinct_authors < 2`. Both prompts produce the identical insufficient report:

```json
{
  "narrative": "",
  "speaker_arcs": [],
  "summary": "Insufficient conversation for dynamics analysis: fewer than two distinct speakers participated, so no cross-speaker trajectory can be summarized.",
  "tone_labels": [],
  "per_speaker_notes": {},
  "insufficient_conversation": true
}
```

Sidebar renders the canned copy: *"Not enough back-and-forth to read the room
here."*

## Qualitative read (sign-off)

The new register lands. On both Transcript 1 and Transcript 2 the contrast
between OLD and NEW is exactly what we wanted: OLD reads like an essay
("provides clarifying details that emphasize their feelings of betrayal",
"effectively use polite disagreement, concession, and synthesis to
collectively refine their understanding"), NEW reads like a person describing a
thread to a friend ("kicks off a brisk, mildly combative side-debate",
"newcomer gently calls out the bickering", "gracefully takes the L"). The NEW
output stays out of content specifics — no mention of the relationship
substance in Transcript 1 or the framework-vs-Next.js subject in Transcript 2,
which is the whole point of the redirect away from ConvoKit's "do not restate
topics" guardrail toward a positive description of conversation shape.
`speaker_arcs` come back populated with sensible turn ranges and timeline-viz
ready notes; in Transcript 1 the mediator's single-turn `[7, 7]` range
demonstrates the schema correctly handles the boundary case.

One minor regression and one nit. The legacy `per_speaker_notes` map came back
empty on Transcript 2 (filed as a follow-up above; does not affect the
production sidebar render). Tone labels on Transcript 1 dropped the
`combative` pill in favor of `scrappy`/`reconciliatory`, which is on-register
for the new voice but slightly less clinical — judgment call, fine to ship.
Approved for merge.
