# Vendored prompts

## `scd_prompt.txt`

Speaker Conversational Dynamics (SCD) trajectory-summary prompt, vendored
verbatim from Cornell NLP's ConvoKit project.

- Source: https://github.com/CornellNLP/ConvoKit/blob/master/convokit/convo_similarity/prompts/scd_prompt.txt
- Upstream project: https://github.com/CornellNLP/ConvoKit
- License: BSD-3-Clause (see `LICENSE.md` at the ConvoKit repo root)

The prompt produces short trajectory summaries of online conversations that
emphasize sentiment, intent, and conversational strategies while avoiding
specific topics or claims. The `{formatted_object}` placeholder in the original
prompt is where the formatted conversation transcript is interpolated before
the LLM call.

### Modifications from upstream

The vendored file is byte-identical to the ConvoKit source except for
normalization applied by this repo's pre-commit hooks:

- Trailing whitespace on individual lines is stripped. Upstream uses trailing
  spaces as Markdown soft breaks; these are invisible to the LLM.
- A single terminating newline is added at end-of-file.

No prompt semantics are altered.

### ConvoKit attribution / copyright notice

Copyright (c) 2017, Cornell University All rights reserved. Redistribution
and use in source and binary forms, with or without modification, are
permitted under the terms of the BSD-3-Clause license. See the upstream
`LICENSE.md` for the full text.
