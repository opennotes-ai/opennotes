from src.simulation.agent import action_selector, sim_agent


class TestAgentInstrumentation:
    def test_sim_agent_has_instrument_enabled(self) -> None:
        assert sim_agent.instrument is True

    def test_action_selector_has_instrument_enabled(self) -> None:
        assert action_selector.instrument is True
