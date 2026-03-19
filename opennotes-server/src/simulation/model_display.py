from __future__ import annotations

import re

PROVIDER_PREFIXES = re.compile(
    r"^(vertex_ai|azure|bedrock|openrouter|azure_ai|together_ai|fireworks_ai|deepinfra|anyscale|palm)/"
)

VENDOR_DOT_PREFIX = re.compile(r"^(anthropic|google|meta|mistral|amazon|cohere|ai21)\.")

FAMILY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^gemini[-\s]", re.IGNORECASE), "Google"),
    (re.compile(r"^gpt[-\s]", re.IGNORECASE), "OpenAI"),
    (re.compile(r"^claude[-\s]", re.IGNORECASE), "Anthropic"),
    (re.compile(r"^mistral[-\s]", re.IGNORECASE), "Mistral"),
    (re.compile(r"^llama[-\s]", re.IGNORECASE), "Meta"),
    (re.compile(r"^command[-\s]", re.IGNORECASE), "Cohere"),
]

VENDOR_DISPLAY: dict[str, str] = {
    "anthropic": "Anthropic",
    "google": "Google",
    "meta": "Meta",
    "mistral": "Mistral",
    "amazon": "Amazon",
    "cohere": "Cohere",
    "ai21": "AI21",
}

UPPERCASE_TOKENS: dict[str, str] = {
    "gpt": "GPT",
    "ai": "AI",
    "llm": "LLM",
}

DIGIT_ONLY = re.compile(r"^\d+$")


def _title_part(part: str) -> str:
    lower = part.lower()
    if lower in UPPERCASE_TOKENS:
        return UPPERCASE_TOKENS[lower]
    return part.capitalize()


def _format_model_slug(slug: str) -> str:
    parts = slug.split("-")
    merged: list[str] = []
    i = 0
    while i < len(parts):
        if not parts[i]:
            i += 1
            continue
        if DIGIT_ONLY.match(parts[i]):
            digits = [parts[i]]
            while i + 1 < len(parts) and DIGIT_ONLY.match(parts[i + 1]):
                digits.append(parts[i + 1])
                i += 1
            merged.append(".".join(digits))
        else:
            merged.append(_title_part(parts[i]))
        i += 1
    return " ".join(merged)


def humanize_model_name(raw: str) -> str:
    if not raw:
        return ""

    name = PROVIDER_PREFIXES.sub("", raw)

    vendor_prefix = ""
    m = VENDOR_DOT_PREFIX.match(name)
    if m:
        vendor_prefix = VENDOR_DISPLAY.get(m.group(1), m.group(1).capitalize())
        name = name[m.end() :]

    if not vendor_prefix:
        for pattern, vendor in FAMILY_RULES:
            if pattern.search(name):
                vendor_prefix = vendor
                break

    if not vendor_prefix:
        return raw

    formatted = _format_model_slug(name)
    return f"{vendor_prefix} {formatted}"
