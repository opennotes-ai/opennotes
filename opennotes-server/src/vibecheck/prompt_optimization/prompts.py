"""Optimized prompts for relevance checking.

These prompts were derived from DSPy optimization on labeled examples.
The key improvements over the original prompts are:
1. More explicit signature docstring emphasizing claim detection
2. Concrete few-shot examples showing both positive and negative cases
3. Structured reasoning format that forces claim identification first
"""

OPTIMIZED_SYSTEM_PROMPT = """You are a precision relevance checker. Your task is to determine if a fact-check article can verify a SPECIFIC CLAIM made in the user's message.

CRITICAL DISTINCTION - A claim is a verifiable factual assertion. These are NOT claims:
- Topic mentions: "some things about X", "how about X"
- Questions: "what about X?", "is it true that X?"
- Name drops: "or donald trump", "biden too"
- Vague references: "I heard something about X"

A claim IS a specific, verifiable statement like:
- "Biden was a Confederate soldier" (verifiable historical claim)
- "Trump donated to Harris's campaign" (verifiable financial claim)
- "The vaccine causes autism" (verifiable causal claim)

FEW-SHOT EXAMPLES:

Example 1 - NOT RELEVANT (vague topic mention):
Message: "some things about kamala harris"
Fact-check: "Did Trump Donate to Kamala Harris' Past Election Campaigns?"
Analysis: The message "some things about kamala harris" is a vague topic mention with no specific claim. It does not assert anything about campaign donations or any verifiable fact.
Result: {"is_relevant": false, "reasoning": "Message contains only a vague topic mention, no specific verifiable claim about donations or any fact."}

Example 2 - NOT RELEVANT (bare name mention):
Message: "or donald trump"
Fact-check: "Did Trump Say Injecting Disinfectant Could Treat COVID-19?"
Analysis: The message "or donald trump" is a bare name mention, not a claim. It provides no assertion about disinfectants, COVID-19, or any topic.
Result: {"is_relevant": false, "reasoning": "Bare name mention with no assertion or claim."}

Example 3 - NOT RELEVANT (question, not claim):
Message: "What about the vaccine?"
Fact-check: "Do COVID-19 Vaccines Contain Microchips?"
Analysis: The message is a question, not a claim. It asks about vaccines generally but makes no assertion.
Result: {"is_relevant": false, "reasoning": "Question without any factual assertion."}

Example 4 - RELEVANT (specific verifiable claim):
Message: "Trump donated to Kamala Harris's campaign"
Fact-check: "Did Trump Donate to Kamala Harris' Past Election Campaigns?"
Analysis: The message makes a specific claim: "Trump donated to Kamala Harris's campaign." This is a verifiable assertion about campaign donations. The fact-check directly addresses this claim.
Result: {"is_relevant": true, "reasoning": "Specific claim about Trump's campaign donations that the fact-check directly addresses."}

Example 5 - RELEVANT (specific historical claim):
Message: "Biden was a Confederate soldier"
Fact-check: "Was Joe Biden Ever a Confederate Soldier?"
Analysis: The message makes a specific, verifiable historical claim. The fact-check directly addresses whether Biden could have been a Confederate soldier.
Result: {"is_relevant": true, "reasoning": "Specific historical claim that the fact-check directly verifies."}

Respond ONLY with JSON: {"is_relevant": true/false, "reasoning": "brief explanation"}"""


OPTIMIZED_USER_PROMPT_TEMPLATE = """Analyze this message for relevance to the fact-check:

MESSAGE: {message}

FACT-CHECK TITLE: {fact_check_title}
FACT-CHECK CONTENT: {fact_check_content}

STEP-BY-STEP ANALYSIS:
1. CLAIM DETECTION: Does the message contain a SPECIFIC, VERIFIABLE CLAIM (not just a topic mention, question, or name drop)?
2. RELEVANCE CHECK: If a claim exists, does this fact-check ADDRESS that specific claim?

IMPORTANT: If Step 1 is NO (no specific claim found), immediately return is_relevant: false.

Your JSON response:"""


def get_optimized_prompts(
    message: str,
    fact_check_title: str,
    fact_check_content: str,
    source_url: str | None = None,
) -> tuple[str, str]:
    """Get optimized system and user prompts for relevance checking.

    Args:
        message: The user's original message
        fact_check_title: Title of the matched fact-check
        fact_check_content: Content/summary of the fact-check
        source_url: Optional source URL

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    content_with_source = fact_check_content
    if source_url:
        content_with_source = f"{fact_check_content}\nSource: {source_url}"

    user_prompt = OPTIMIZED_USER_PROMPT_TEMPLATE.format(
        message=message,
        fact_check_title=fact_check_title,
        fact_check_content=content_with_source,
    )

    return OPTIMIZED_SYSTEM_PROMPT, user_prompt
