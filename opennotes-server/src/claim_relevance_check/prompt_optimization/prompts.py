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
Message: "Trump donated to Kamala Harris's campaign"
Fact-check: "Did Trump Donate to Kamala Harris' Past Election Campaigns?"
Reasoning: The message makes a specific claim: 'Trump donated to Kamala Harris's campaign.' This is a verifiable assertion. The fact-check directly addresses this claim and confirms Trump made donations totaling $6,000.
Result: {"is_relevant": true, "reasoning": "The message makes a specific claim: 'Trump donated to Kamala Harris's campaign.' This is a verifiabl..."}

Example 2 - RELEVANT:
Message: "The vaccine causes autism"
Fact-check: "Do Vaccines Cause Autism?"
Reasoning: The message makes a specific causal claim: 'The vaccine causes autism.' This is a verifiable factual assertion. The fact-check directly addresses whether vaccines cause autism.
Result: {"is_relevant": true, "reasoning": "The message makes a specific causal claim: 'The vaccine causes autism.' This is a verifiable factual..."}

Example 3 - NOT RELEVANT:
Message: "What about the vaccine?"
Fact-check: "Do COVID-19 Vaccines Contain Microchips?"
Reasoning: The message is a question, not a claim. It asks about 'the vaccine' generally but makes no assertion about microchips or any specific claim that could be verified.
Result: {"is_relevant": false, "reasoning": "The message is a question, not a claim. It asks about 'the vaccine' generally but makes no assertion..."}

Example 4 - NOT RELEVANT:
Message: "some things about kamala harris"
Fact-check: "Did Trump Donate to Kamala Harris' Past Election Campaigns?"
Reasoning: The message 'some things about kamala harris' is a vague topic mention with no specific claim. It does not assert anything about campaign donations or any verifiable fact. The fact-check about Trump's donations is completely unrelated to anything stated in the message.
Result: {"is_relevant": false, "reasoning": "The message 'some things about kamala harris' is a vague topic mention with no specific claim. It do..."}

Example 5 - NOT RELEVANT:
Message: "or donald trump"
Fact-check: "Did Trump Say Injecting Disinfectant Could Treat COVID-19?"
Reasoning: The message 'or donald trump' is a bare name mention, not a claim. It provides no assertion about disinfectants, COVID-19, or any other topic. Cannot be fact-checked.
Result: {"is_relevant": false, "reasoning": "The message 'or donald trump' is a bare name mention, not a claim. It provides no assertion about di..."}

Example 6 - RELEVANT:
Message: "Biden was a Confederate soldier"
Fact-check: "Was Joe Biden Ever a Confederate Soldier?"
Reasoning: The message makes a specific, verifiable claim: 'Biden was a Confederate soldier.' This is a factual assertion that can be checked. The fact-check directly addresses this exact claim by examining Biden's birth date vs the Civil War timeline.
Result: {"is_relevant": true, "reasoning": "The message makes a specific, verifiable claim: 'Biden was a Confederate soldier.' This is a factual..."}

Example 7 - NOT RELEVANT:
Message: "how about biden"
Fact-check: "Did Biden Say He Would Ban Fracking?"
Reasoning: The message 'how about biden' is a question/topic shift with no specific claim. It mentions Biden's name but makes no assertion about fracking or any other topic that could be fact-checked.
Result: {"is_relevant": false, "reasoning": "The message 'how about biden' is a question/topic shift with no specific claim. It mentions Biden's ..."}

Example 8 - NOT RELEVANT:
Message: "I heard something about immigrants"
Fact-check: "Are Immigrants Eating Pets in Springfield, Ohio?"
Reasoning: The message is a vague reference ('heard something') with no specific claim. It doesn't mention pets, Springfield, or Haitian immigrants - topics central to the fact-check.
Result: {"is_relevant": false, "reasoning": "The message is a vague reference ('heard something') with no specific claim. It doesn't mention pets..."}

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
