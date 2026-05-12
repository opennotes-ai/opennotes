import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import { OverallRecommendationCard } from "./OverallRecommendationCard";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type WeatherReport = components["schemas"]["WeatherReport"];
type RelevanceLabel = WeatherReport["relevance"]["label"];
type TruthLabel = WeatherReport["truth"]["label"];

function makeWeatherReport(
  truth: TruthLabel,
  relevance: RelevanceLabel,
): WeatherReport {
  return {
    truth: { label: truth },
    relevance: { label: relevance },
    sentiment: { label: "neutral" },
  };
}

afterEach(() => {
  cleanup();
});

function makeRecommendation(
  overrides: Partial<SafetyRecommendation> = {},
): SafetyRecommendation {
  return {
    level: "safe",
    rationale: "No harmful content detected.",
    top_signals: [],
    unavailable_inputs: [],
    ...overrides,
  };
}

function makeFlashpoint(
  overrides: Partial<FlashpointMatch> = {},
): FlashpointMatch {
  return {
    scan_type: "conversation_flashpoint",
    utterance_id: "u1",
    derailment_score: 60,
    risk_level: "Heated",
    reasoning: "test fixture",
    context_messages: 4,
    ...overrides,
  };
}

describe("<OverallRecommendationCard />", () => {
  it("renders 'Overall: OK.' for safe level with top_signals[0] as reason", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["educational context"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: OK.");
    expect(reason.textContent).toBe("educational context");
  });

  it("renders 'Overall: OK.' for mild level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern noted"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: OK.");
  });

  it("renders 'Overall: Flag!' for unsafe level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "unsafe",
          top_signals: ["explicit harmful content found"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: Flag!");
  });

  it("renders 'Overall: Flag!' for caution level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["potentially sensitive material"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: Flag!");
  });

  it("returns null when recommendation is null and overall is absent", () => {
    render(() => (
      <OverallRecommendationCard recommendation={null} />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });

  it("returns null when recommendation is null and overall is null", () => {
    render(() => (
      <OverallRecommendationCard recommendation={null} overall={null} />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });

  it("explicit overall prop overrides derived value", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({ level: "unsafe", top_signals: ["bad content"] })}
        overall={{ verdict: "pass", reason: "manually reviewed", status: "final" }}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: OK.");
    expect(reason.textContent).toBe("manually reviewed");
  });

  it("renders long top_signal verbatim", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [
            "Text moderation flags triggered, but judged to be false positives.",
          ],
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe(
      "Text moderation flags triggered, but judged to be false positives.",
    );
  });

  it("keeps caution flagged but skips raw false-positive score reason", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "text: Legal 1.0",
            "Repeated low-severity toxicity",
          ],
          rationale:
            "Legal, Firearms, and Illicit Drugs scores are judged to be false positives. Repeated low-severity toxicity remains.",
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Flag!");
    expect(reason.textContent).toBe("Repeated low-severity toxicity");
  });

  it("falls back to remaining rationale concern when first signal is a false-positive score", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["text: Legal 1.0"],
          rationale:
            "Legal, Firearms, and Illicit Drugs scores are judged to be false positives. Mild violent rhetoric remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Mild violent rhetoric remains");
  });

  it("finds remaining rationale concern after false-positive but clause", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["text: Legal 1.0"],
          rationale:
            "Legal score is judged to be false positive, but repeated low-severity toxicity remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("repeated low-severity toxicity remains");
  });

  it("falls back to rationale first clause when top_signals is empty", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [],
          rationale: "Content is safe, no issues found.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Content is safe");
  });

  it("renders rationale first clause without word truncation", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [],
          rationale: "Text moderation flags triggered but judged false positives, no issues found.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe(
      "Text moderation flags triggered but judged false positives",
    );
  });

  it("whitespace-only top_signals[0] falls back to rationale", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["   "],
          rationale: "Safe content verified.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Safe content verified");
  });

  it("empty rationale and no signals returns null (card not rendered)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [],
          rationale: "",
        })}
      />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });

  it("does not treat benign integer-trailing signals as raw moderation scores", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["Phishing link 1"],
          rationale:
            "Moderation flags judged to be false positives. Some risk remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Phishing link 1");
  });

  it("does not treat year-trailing signals as raw moderation scores", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["Adult imagery 2024"],
          rationale:
            "Moderation flags judged to be false positives. Concerns remain.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Adult imagery 2024");
  });

  it("suppresses 'text: Firearms & Weapons 0.769' (ampersand in category)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "text: Legal 1.0",
            "text: Firearms & Weapons 0.769",
            "Repeated low-severity toxicity",
          ],
          rationale:
            "Legal and Firearms & Weapons scores are clearly false positives. Repeated low-severity toxicity remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Repeated low-severity toxicity");
  });

  it("suppresses 'text: Death, Harm & Tragedy 0.85' (comma + ampersand)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "text: Death, Harm & Tragedy 0.85",
            "Repeated low-severity toxicity",
          ],
          rationale:
            "Death, Harm & Tragedy score is judged to be a false positive. Repeated low-severity toxicity remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Repeated low-severity toxicity");
  });

  it("suppresses 'image: max_likelihood 0.25' (image prefix)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "image: max_likelihood 0.25",
            "Repeated low-severity toxicity",
          ],
          rationale:
            "Image scores judged to be false positives. Repeated low-severity toxicity remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Repeated low-severity toxicity");
  });

  it("suppresses 'Firearms & Weapons 0.769' without text: prefix", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "Firearms & Weapons 0.769",
            "Repeated low-severity toxicity",
          ],
          rationale: "Firearms score judged to be a false positive. Repeated low-severity toxicity remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Repeated low-severity toxicity");
  });

  it("does not classify humanized prose like 'Mild violent rhetoric' as raw", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["text: Legal 1.0", "Mild violent rhetoric"],
          rationale: "Legal score judged to be a false positive. Mild violent rhetoric remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Mild violent rhetoric");
  });

  it("reproduces production job 9c9dafb1 — surfaces humanized concern over raw scores", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "text: Legal 1.0",
            "text: Firearms & Weapons 0.769",
            "text: Illicit Drugs 0.7",
            "text: Toxic 0.674",
            "image: max_likelihood 0.25",
          ],
          rationale:
            "The text analysis returned multiple high-scoring matches (Legal 1.0, Firearms & Weapons 0.769, Illicit Drugs 0.7), but these are clearly false positives triggered by programming languages and tech terminology. However, the text also contains multiple verified low-severity signals of toxicity and mild violence from users venting, which together warrant a caution rating.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    // Must not be any of the raw-score top_signals.
    expect(reason.textContent).not.toMatch(/\d+\.\d+/);
    expect(reason.textContent).not.toMatch(/^(?:text|image|video):/i);
    // Must surface the real concern from the rationale (toxicity / venting),
    // not a broken decimal-split fragment like "Legal 1".
    expect(reason.textContent).toMatch(/toxicity|venting|violence/i);
  });

  it("does not surface single-letter abbreviation fragments like 'g' from 'e.g.'", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["text: Legal 1.0", "text: Firearms 0.769"],
          rationale:
            "The text analysis returned multiple high-scoring matches (e.g. Legal 1.0, Firearms 0.769) which are clearly false positives.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent?.trim().length ?? 0).toBeGreaterThan(2);
    expect(reason.textContent).not.toBe("g");
    expect(reason.textContent).not.toBe("e");
  });

  it("reproduces exact prod 9c9dafb1 rationale — no 'g' fragment, surfaces real concern", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: [
            "text: Legal 1.0",
            "text: Firearms & Weapons 0.769",
            "text: Illicit Drugs 0.7",
            "text: Toxic 0.674",
            "image: max_likelihood 0.25",
          ],
          rationale:
            'The text analysis returned multiple high-scoring matches (Legal 1.0, Firearms & Weapons 0.769, Illicit Drugs 0.7), but these are clearly false positives triggered by programming languages and tech terminology (e.g., Rust, Julia, CUDA, LLMs). However, the text also contains multiple verified low-severity signals of toxicity and mild violence (e.g., "brisk kick in the rear", "dies an agonising, painful death") from users venting, which together warrant a caution rating. Image moderation scores are low.',
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).not.toBe("g");
    expect(reason.textContent).not.toBe("e");
    expect(reason.textContent?.trim().length ?? 0).toBeGreaterThan(5);
    expect(reason.textContent).toMatch(/toxicity|venting|violence|caution/i);
  });

  it("falls back to humanized default when every rationale clause is suppressed", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["text: Legal 1.0"],
          rationale:
            "Legal 1.0 is judged to be a false positive. Firearms 0.769 also false positive.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Multiple low-severity concerns");
  });

  it("still suppresses decimal-scored signals when rationale is FP", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["text: Legal 1.0", "Repeated low-severity toxicity"],
          rationale:
            "Legal scores are judged to be false positives. Repeated low-severity toxicity remains.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Repeated low-severity toxicity");
  });

  it("empty-leading top_signal yields next non-empty signal (PR #554 .find precedence)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["", "Real signal"],
          rationale: "Should not fall through to rationale.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Real signal");
  });

  it("reason span has truncate constraint and title tooltip for overflow", () => {
    const longSignal =
      "An extremely long top signal description that would otherwise push the verdict row outside of the card boundary on narrow viewports";
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [longSignal],
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.className).toContain("truncate");
    expect(reason.className).toContain("min-w-0");
    expect(reason.getAttribute("title")).toBe(longSignal);
  });

  it("mild + no flashpoint matches preserves Overall: OK.", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: OK.");
  });

  it("mild + Low Risk flashpoint preserves Overall: OK.", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
        flashpointMatches={[makeFlashpoint({ risk_level: "Low Risk" })]}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: OK.");
  });

  it("mild + Heated flashpoint escalates to Overall: Flag!", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
        flashpointMatches={[makeFlashpoint({ risk_level: "Heated" })]}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Flag!");
    expect(reason.textContent).toBe("Conversation flashpoint risk: Heated");
  });

  it("mild + Hostile flashpoint escalates to Overall: Flag!", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
        flashpointMatches={[makeFlashpoint({ risk_level: "Hostile" })]}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Flag!");
    expect(reason.textContent).toBe("Conversation flashpoint risk: Hostile");
  });

  it("mild + multiple flashpoints picks highest risk", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
        flashpointMatches={[
          makeFlashpoint({ risk_level: "Heated", utterance_id: "u1" }),
          makeFlashpoint({ risk_level: "Dangerous", utterance_id: "u2" }),
        ]}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Flag!");
    expect(reason.textContent).toBe("Conversation flashpoint risk: Dangerous");
  });

  it("safe + Dangerous flashpoint is NOT escalated (only mild is)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["all clear"],
        })}
        flashpointMatches={[makeFlashpoint({ risk_level: "Dangerous" })]}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: OK.");
  });

  it("explicit overall prop overrides flashpoint escalation", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
        flashpointMatches={[makeFlashpoint({ risk_level: "Dangerous" })]}
        overall={{ verdict: "pass", reason: "manually reviewed", status: "final" }}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: OK.");
    expect(reason.textContent).toBe("manually reviewed");
  });

  it("escalates Pass to Flag when weather report is misleading + on_topic", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["educational context"],
        })}
        weatherReport={makeWeatherReport("misleading", "on_topic")}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Flag!");
    expect(reason.textContent).toBe("Misleading framing in on-topic discussion");
  });

  it("escalates Pass to Flag when weather report is misleading + insightful", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern"],
        })}
        weatherReport={makeWeatherReport("misleading", "insightful")}
      />
    ));

    expect(screen.getByTestId("overall-recommendation-verdict").textContent).toBe(
      "Overall: Flag!",
    );
  });

  it("does not escalate when truth is misleading but relevance is off_topic", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["educational context"],
        })}
        weatherReport={makeWeatherReport("misleading", "off_topic")}
      />
    ));

    expect(screen.getByTestId("overall-recommendation-verdict").textContent).toBe(
      "Overall: OK.",
    );
  });

  it("does not escalate when truth is hearsay (only 'misleading' triggers)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["educational context"],
        })}
        weatherReport={makeWeatherReport("hearsay", "on_topic")}
      />
    ));

    expect(screen.getByTestId("overall-recommendation-verdict").textContent).toBe(
      "Overall: OK.",
    );
  });

  it("does not downgrade an existing Flag verdict even with misleading + on_topic", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "unsafe",
          top_signals: ["explicit threat"],
        })}
        weatherReport={makeWeatherReport("misleading", "on_topic")}
      />
    ));

    expect(screen.getByTestId("overall-recommendation-verdict").textContent).toBe(
      "Overall: Flag!",
    );
  });

  it("explicit overall prop wins over weather report escalation", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["educational context"],
        })}
        weatherReport={makeWeatherReport("misleading", "on_topic")}
        overall={{ verdict: "pass", reason: "manually reviewed", status: "final" }}
      />
    ));

    expect(screen.getByTestId("overall-recommendation-verdict").textContent).toBe(
      "Overall: OK.",
    );
  });

  it("whitespace-only rationale and no signals returns null (card not rendered)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["   "],
          rationale: "   ",
        })}
      />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });
});
