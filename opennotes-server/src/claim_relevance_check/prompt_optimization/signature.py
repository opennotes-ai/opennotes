"""DSPy signature definition for relevance checking."""

import dspy


class RelevanceCheck(dspy.Signature):
    """Determine if a fact-check can verify a SPECIFIC CLAIM in the user's message.

    A claim is a verifiable assertion of fact, NOT:
    - A topic mention ("some things about X")
    - A question ("what about X?")
    - A name drop ("or donald trump")
    - An opinion without factual content

    Only return is_relevant=True if the message contains a specific, verifiable claim
    AND the fact-check directly addresses that claim.
    """

    message: str = dspy.InputField(desc="The user's original message to evaluate")
    fact_check_title: str = dspy.InputField(desc="Title of the matched fact-check article")
    fact_check_content: str = dspy.InputField(desc="Summary/content of the fact-check article")

    is_relevant: bool = dspy.OutputField(
        desc="True ONLY if: (1) message contains a specific verifiable claim, AND (2) this fact-check addresses that exact claim"
    )
    reasoning: str = dspy.OutputField(
        desc="Explain: 1) What specific claim exists in the message (if any), 2) Whether the fact-check addresses it"
    )
