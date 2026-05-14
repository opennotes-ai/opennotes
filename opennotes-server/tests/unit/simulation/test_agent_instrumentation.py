from pydantic_ai.capabilities import Instrumentation

from src.simulation.agent import action_selector, sim_agent


class TestAgentInstrumentation:
    def test_sim_agent_has_instrument_enabled(self) -> None:
        assert any(
            isinstance(capability, Instrumentation)
            for capability in sim_agent.root_capability.capabilities
        )

    def test_action_selector_has_instrument_enabled(self) -> None:
        assert any(
            isinstance(capability, Instrumentation)
            for capability in action_selector.root_capability.capabilities
        )
