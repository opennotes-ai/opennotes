"""Dataset loading utilities for relevance check training."""

import json
from dataclasses import dataclass
from pathlib import Path

import dspy


@dataclass
class RelevanceExample:
    """A labeled example for relevance checking."""

    example_id: str
    message: str
    fact_check_title: str
    fact_check_content: str
    is_relevant: bool
    reasoning: str

    def to_dspy_example(self) -> dspy.Example:
        """Convert to a DSPy Example with proper input/output field marking."""
        return dspy.Example(
            message=self.message,
            fact_check_title=self.fact_check_title,
            fact_check_content=self.fact_check_content,
            is_relevant=self.is_relevant,
            reasoning=self.reasoning,
        ).with_inputs("message", "fact_check_title", "fact_check_content")


TRAINING_EXAMPLES = [
    RelevanceExample(
        example_id="fp-001",
        message="some things about kamala harris",
        fact_check_title="Did Trump Donate to Kamala Harris' Past Election Campaigns?",
        fact_check_content="U.S. President Donald Trump donated $6,000 to Kamala Harris' 2014 campaign for reelection as California attorney general. Records show Trump made contributions in 2011 and 2013.",
        is_relevant=False,
        reasoning="The message 'some things about kamala harris' is a vague topic mention with no specific claim. It does not assert anything about campaign donations or any verifiable fact. The fact-check about Trump's donations is completely unrelated to anything stated in the message.",
    ),
    RelevanceExample(
        example_id="fp-002",
        message="how about biden",
        fact_check_title="Did Biden Say He Would Ban Fracking?",
        fact_check_content="Joe Biden's position on fracking has been complex. During debates he stated he would not ban fracking, though he supports transitioning away from fossil fuels.",
        is_relevant=False,
        reasoning="The message 'how about biden' is a question/topic shift with no specific claim. It mentions Biden's name but makes no assertion about fracking or any other topic that could be fact-checked.",
    ),
    RelevanceExample(
        example_id="fp-003",
        message="or donald trump",
        fact_check_title="Did Trump Say Injecting Disinfectant Could Treat COVID-19?",
        fact_check_content="During a White House briefing, Trump suggested research into whether disinfectants could be used to treat COVID-19 internally.",
        is_relevant=False,
        reasoning="The message 'or donald trump' is a bare name mention, not a claim. It provides no assertion about disinfectants, COVID-19, or any other topic. Cannot be fact-checked.",
    ),
    RelevanceExample(
        example_id="fp-004",
        message="What about the vaccine?",
        fact_check_title="Do COVID-19 Vaccines Contain Microchips?",
        fact_check_content="Claims that COVID-19 vaccines contain microchips are false. Vaccines contain mRNA or viral proteins but no tracking devices.",
        is_relevant=False,
        reasoning="The message is a question, not a claim. It asks about 'the vaccine' generally but makes no assertion about microchips or any specific claim that could be verified.",
    ),
    RelevanceExample(
        example_id="fp-005",
        message="I heard something about immigrants",
        fact_check_title="Are Immigrants Eating Pets in Springfield, Ohio?",
        fact_check_content="Claims that Haitian immigrants in Springfield, Ohio are eating pets have been debunked by local officials and police.",
        is_relevant=False,
        reasoning="The message is a vague reference ('heard something') with no specific claim. It doesn't mention pets, Springfield, or Haitian immigrants - topics central to the fact-check.",
    ),
    RelevanceExample(
        example_id="tp-001",
        message="Biden was a Confederate soldier",
        fact_check_title="Was Joe Biden Ever a Confederate Soldier?",
        fact_check_content="Joe Biden was born in 1942, decades after the Civil War ended in 1865. It is impossible for him to have been a Confederate soldier.",
        is_relevant=True,
        reasoning="The message makes a specific, verifiable claim: 'Biden was a Confederate soldier.' This is a factual assertion that can be checked. The fact-check directly addresses this exact claim by examining Biden's birth date vs the Civil War timeline.",
    ),
    RelevanceExample(
        example_id="tp-002",
        message="Trump donated to Kamala Harris's campaign",
        fact_check_title="Did Trump Donate to Kamala Harris' Past Election Campaigns?",
        fact_check_content="U.S. President Donald Trump donated $6,000 to Kamala Harris' 2014 campaign for reelection as California attorney general.",
        is_relevant=True,
        reasoning="The message makes a specific claim: 'Trump donated to Kamala Harris's campaign.' This is a verifiable assertion. The fact-check directly addresses this claim and confirms Trump made donations totaling $6,000.",
    ),
    RelevanceExample(
        example_id="tp-003",
        message="The vaccine causes autism",
        fact_check_title="Do Vaccines Cause Autism?",
        fact_check_content="Multiple large-scale studies have found no link between vaccines and autism. The original study claiming a link was retracted and its author lost his medical license.",
        is_relevant=True,
        reasoning="The message makes a specific causal claim: 'The vaccine causes autism.' This is a verifiable factual assertion. The fact-check directly addresses whether vaccines cause autism.",
    ),
    RelevanceExample(
        example_id="tp-004",
        message="Haitian immigrants are eating cats and dogs in Ohio",
        fact_check_title="Are Immigrants Eating Pets in Springfield, Ohio?",
        fact_check_content="Claims that Haitian immigrants in Springfield, Ohio are eating pets have been debunked by local officials and police who found no evidence.",
        is_relevant=True,
        reasoning="The message makes a specific claim about Haitian immigrants eating pets in Ohio. The fact-check directly addresses this exact claim about Springfield, Ohio.",
    ),
    RelevanceExample(
        example_id="tp-005",
        message="Trump said we should inject bleach to cure COVID",
        fact_check_title="Did Trump Say Injecting Disinfectant Could Treat COVID-19?",
        fact_check_content="During a White House briefing, Trump suggested research into whether disinfectants could be used internally. He did not use the word 'bleach' but referenced disinfectant.",
        is_relevant=True,
        reasoning="The message makes a specific claim about something Trump said regarding injecting substances to treat COVID. The fact-check addresses Trump's comments about disinfectants during the briefing.",
    ),
]


def load_training_examples() -> list[dspy.Example]:
    """Load all training examples as DSPy Examples."""
    return [ex.to_dspy_example() for ex in TRAINING_EXAMPLES]


def load_examples_from_json(json_path: Path) -> list[dspy.Example]:
    """Load examples from a JSON file."""
    with json_path.open() as f:
        data = json.load(f)

    examples = data if isinstance(data, list) else [data]

    result = []
    for item in examples:
        ex = RelevanceExample(
            example_id=item.get("example_id", "unknown"),
            message=item["original_message"],
            fact_check_title=item["fact_check"]["title"],
            fact_check_content=item["fact_check"]["content"][:500],
            is_relevant=item["expected_is_relevant"],
            reasoning=item["expected_reasoning"],
        )
        result.append(ex.to_dspy_example())

    return result


def get_train_test_split(
    test_ratio: float = 0.2,
) -> tuple[list[dspy.Example], list[dspy.Example]]:
    """Split examples into train and test sets."""
    examples = load_training_examples()
    n_test = max(1, int(len(examples) * test_ratio))
    return examples[:-n_test], examples[-n_test:]
