import pytest


@pytest.fixture(autouse=True, scope="session")
def _register_simulation_models():
    from src.community_config.models import CommunityConfig  # noqa: F401
    from src.llm_config.models import CommunityServer, CommunityServerLLMConfig  # noqa: F401
    from src.notes.models import Note  # noqa: F401
    from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost  # noqa: F401
    from src.simulation.models import (  # noqa: F401
        SimAgent,
        SimAgentInstance,
        SimAgentMemory,
        SimulationOrchestrator,
        SimulationRun,
    )
    from src.users.models import User  # noqa: F401
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile  # noqa: F401
