"""
Conftest for property-based tests.

These tests don't require the full application fixture, just the schemas and scoring modules.
"""

from hypothesis import Verbosity, settings

settings.register_profile("dev", max_examples=50, verbosity=Verbosity.verbose)
settings.register_profile("ci", max_examples=100)
settings.load_profile("dev")
