"""Optimized prompts for relevance checking.

AUTO-GENERATED from optimized_relevance_module.json
Do not edit manually - run compare_and_update.py to regenerate.
"""

OPTIMIZED_SYSTEM_PROMPT = """Determine if a fact-check can verify a SPECIFIC CLAIM in the user's message.

A claim is a verifiable assertion of fact, NOT:
- A topic mention ("some things about X")
- A question ("what about X?")
- A name drop ("or donald trump")
- An opinion without factual content

Only return is_relevant=True if the message contains a specific, verifiable claim
AND the fact-check directly addresses that claim.

FEW-SHOT EXAMPLES:

Example 1 - RELEVANT:
Message: "Haitian immigrants are eating cats and dogs in Ohio"
Fact-check: "Are Immigrants Eating Pets in Springfield, Ohio?"
Result: {"is_relevant": true, "reasoning": "The message asserts a specific, verifiable factual claim: that Haitian immigrants in Ohio are eating..."}

Example 2 - NOT RELEVANT:
Message: "I've been following the news about climate change lately. It's really concerning how much debate there is. What do you think about renewable energy?"
Fact-check: "Did Scientists Predict an Ice Age in the 1970s?"
Result: {"is_relevant": false, "reasoning": "The user message is a general comment and question about climate change and renewable energy, not a ..."}

Example 3 - RELEVANT:
Message: "I was talking to my uncle at Thanksgiving and he kept insisting that the COVID vaccines have killed more people than COVID itself. Is that even possible?"
Fact-check: "Have COVID-19 Vaccines Killed More People Than COVID-19?"
Result: {"is_relevant": true, "reasoning": "The message relays a specific, verifiable claim: that COVID-19 vaccines have killed more people than..."}

Example 4 - RELEVANT:
Message: "Did you hear? They found proof that the moon landing was faked"
Fact-check: "Was the Apollo 11 Moon Landing Faked?"
Result: {"is_relevant": true, "reasoning": "The message asserts (albeit via hearsay) a specific verifiable claim: that “they found proof that th..."}

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
        content_with_source = fact_check_content + "\nSource: " + source_url

    user_prompt = OPTIMIZED_USER_PROMPT_TEMPLATE.format(
        message=message,
        fact_check_title=fact_check_title,
        fact_check_content=content_with_source,
    )

    return OPTIMIZED_SYSTEM_PROMPT, user_prompt
