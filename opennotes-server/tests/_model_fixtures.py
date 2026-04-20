"""Shared model strings for tests. Use these instead of hardcoded literals.

Constants -- for 'I need any google model to exercise parsing' behavior.
Fixture (prod_default_google_model in conftest) -- for 'assert on the live
production default'.

The distinction matters: tests that only need *a* model string to exercise
parsing, routing, or adapter code should import the constants here. Tests
that must track whichever model production is actually configured to use
should depend on the ``prod_default_google_model`` fixture so they stay
in lockstep with ``src.llm_config.constants.DEFAULT_MODELS_BY_PROVIDER``.

This module intentionally avoids importing from ``src.*`` at module level
so it can be imported by tests that run before app configuration.
"""

GOOGLE_VERTEX_PRO_TEST_MODEL = "google-vertex:gemini-3.1-pro-preview"
GOOGLE_VERTEX_FLASH_TEST_MODEL = "google-vertex:gemini-3-flash"
OPENAI_TEST_MODEL = "openai:gpt-4o-mini"
ANTHROPIC_TEST_MODEL = "anthropic:claude-3-haiku-20240307"
GROQ_TEST_MODEL = "groq:llama-3.3-70b-versatile"
