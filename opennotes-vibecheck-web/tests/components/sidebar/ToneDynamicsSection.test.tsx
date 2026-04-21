import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import ToneDynamicsSection from "../../../src/components/sidebar/ToneDynamicsSection";
import type { components } from "../../../src/lib/generated-types";

type ToneDynamics = components["schemas"]["ToneDynamicsSection"];

afterEach(() => {
  cleanup();
});

describe("<ToneDynamicsSection />", () => {
  it("renders flashpoint matches with risk level and SCD summary/tone labels/speaker notes", () => {
    const toneDynamics: ToneDynamics = {
      flashpoint_matches: [
        {
          scan_type: "conversation_flashpoint",
          utterance_id: "u1",
          derailment_score: 72,
          risk_level: "Heated",
          reasoning: "sharp personal attack after disagreement",
          context_messages: 3,
        },
        {
          scan_type: "conversation_flashpoint",
          utterance_id: "u2",
          derailment_score: 54,
          risk_level: "Guarded",
          reasoning: "defensive tone escalating",
          context_messages: 2,
        },
      ],
      scd: {
        summary: "Heated exchange about editorial choices.",
        tone_labels: ["combative", "dismissive"],
        per_speaker_notes: {
          alice: "repeatedly interrupts",
          bob: "shuts down with sarcasm",
        },
        insufficient_conversation: false,
      },
    };

    render(() => <ToneDynamicsSection toneDynamics={toneDynamics} />);

    expect(screen.getByTestId("flashpoint-entry").textContent).toMatch(
      /Flashpoint \(2\)/,
    );
    const riskLevels = screen
      .getAllByTestId("flashpoint-risk-level")
      .map((el) => el.textContent);
    expect(riskLevels).toEqual(["Heated", "Guarded"]);
    expect(screen.getByText(/sharp personal attack/)).not.toBeNull();

    const scd = screen.getByTestId("scd-entry");
    expect(scd.textContent).toMatch(/Heated exchange/);

    const labels = screen
      .getAllByTestId("scd-tone-label")
      .map((el) => el.textContent);
    expect(labels).toEqual(["combative", "dismissive"]);

    expect(screen.getByText(/repeatedly interrupts/)).not.toBeNull();
    expect(screen.getByText(/shuts down with sarcasm/)).not.toBeNull();
  });

  it("renders 'No flashpoint moments' when flashpoint_matches is empty", () => {
    const toneDynamics: ToneDynamics = {
      flashpoint_matches: [],
      scd: {
        summary: "",
        tone_labels: [],
        per_speaker_notes: {},
        insufficient_conversation: false,
      },
    };

    render(() => <ToneDynamicsSection toneDynamics={toneDynamics} />);
    expect(
      screen.getByText(/No flashpoint moments detected/),
    ).not.toBeNull();
  });

  it("shows insufficient-conversation notice when SCD reports it", () => {
    const toneDynamics: ToneDynamics = {
      flashpoint_matches: [],
      scd: {
        summary: "(placeholder)",
        tone_labels: [],
        per_speaker_notes: {},
        insufficient_conversation: true,
      },
    };

    render(() => <ToneDynamicsSection toneDynamics={toneDynamics} />);
    expect(screen.getByTestId("scd-insufficient")).not.toBeNull();
  });
});
