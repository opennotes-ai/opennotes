# Vendored prompts

## `scd_prompt.txt`

Speaker Conversational Dynamics (SCD) prompt used by `analyze_scd`. The current
file is an **OpenNotes-authored adaptation** that produces vibecheck's
conversational-register output (the `narrative` + `speaker_arcs` fields on
`SCDReport`, alongside the back-compat `summary` / `tone_labels` /
`per_speaker_notes`).

### Provenance

The original `scd_prompt.txt` was vendored verbatim from Cornell NLP's ConvoKit
project as the starting point for this work:

- Source: https://github.com/CornellNLP/ConvoKit/blob/master/convokit/convo_similarity/prompts/scd_prompt.txt
- Upstream project: https://github.com/CornellNLP/ConvoKit
- License: BSD-3-Clause (see `LICENSE.md` at the ConvoKit repo root)

The verbatim ConvoKit version was the only content of this file at every commit
prior to TASK-1471.23.02. To recover it, `git log --follow` this file and check
out any revision before that task's commit.

### Why we adapted it

ConvoKit's prompt produces an academic, transcript-style trajectory summary
(third-person past tense, "Speaker1 attacks Speaker2 by..."). vibecheck surfaces
SCD output in a sidebar where it sits next to claim-level analyses; users
reported the original voice felt like an anthropologist's field notes. The
adapted prompt asks for the same structural intent — sentiment, intent, and
conversational strategies, with content specifics suppressed — but in a
conversational register, and additionally produces a structured `speaker_arcs`
list with optional 1-indexed `utterance_id_range` spans for timeline
visualization.

### License

Because the current prompt is a derivative work of a BSD-3-Clause-licensed
input, the BSD-3-Clause notice continues to apply. The Cornell University
copyright/license note from upstream:

> Copyright (c) 2017, Cornell University. All rights reserved. Redistribution
> and use in source and binary forms, with or without modification, are
> permitted under the terms of the BSD-3-Clause license. See the upstream
> `LICENSE.md` for the full text.
