from __future__ import annotations

from pydantic_ai.models.google import GoogleModel

# Compatibility export for call sites that still import the local symbol.
# pydantic-ai 1.96 handles function-tool + native-tool combinations upstream.
OpenNotesGoogleModel = GoogleModel

__all__ = ["OpenNotesGoogleModel"]
