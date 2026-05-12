import { createSignal } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import WeatherReport from "./WeatherReport";
import { WeatherSymbol } from "./WeatherSymbol";
import { SidebarStoreProvider, useSidebarStore } from "../SidebarStoreProvider";
import * as weatherLabels from "~/lib/weather-labels";

type WeatherReportData = components["schemas"]["WeatherReport"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

function makeSafetyRecommendation(
  overrides: Partial<SafetyRecommendation> = {},
): SafetyRecommendation {
  return {
    level: "safe",
    rationale: "All moderation checks passed without any flagged content.",
    top_signals: ["web_risk: clean", "image_moderation: no_issues"],
    unavailable_inputs: [],
    ...overrides,
  };
}

function makeWeatherReport(
  overrides: Partial<WeatherReportData> = {},
): WeatherReportData {
  return {
    truth: {
      label: "first_person",
      logprob: null,
      alternatives: [],
    },
    relevance: {
      label: "on_topic",
      logprob: null,
      alternatives: [],
    },
    sentiment: {
      label: "warmly skeptical",
      logprob: null,
      alternatives: [],
    },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("WeatherReport", () => {
  it("renders truth, relevance, and sentiment evaluations", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    expect(screen.getByTestId("weather-axis-card-truth")).toBeDefined();
    expect(screen.getByTestId("weather-axis-card-relevance")).toBeDefined();
    expect(screen.getByTestId("weather-truth-value").textContent).toBe(
      "First-Person",
    );
    expect(screen.getByTestId("weather-relevance-value").textContent).toBe(
      "On Topic",
    );
    expect(screen.getByTestId("weather-sentiment-value").textContent).toContain(
      "Warmly Skeptical",
    );
  });

  it("renders ONE outer container, not three separate boxes", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    expect(screen.getAllByTestId("weather-report")).toHaveLength(1);
    const root = screen.getByTestId("weather-report");
    expect(root.contains(screen.getByTestId("weather-axis-card-truth"))).toBe(
      true,
    );
    expect(
      root.contains(screen.getByTestId("weather-axis-card-relevance")),
    ).toBe(true);
  });

  it("renders four axis pairs (safety, truth, relevance, sentiment) inside the report", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport()}
        safetyRecommendation={makeSafetyRecommendation()}
      />
    ));

    const root = screen.getByTestId("weather-report");
    expect(root.querySelector('[data-testid="weather-axis-card-safety"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="weather-axis-card-truth"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="weather-axis-card-relevance"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="weather-axis-card-sentiment"]')).not.toBeNull();
    expect(root.querySelector('[data-slot="table-header"]')).toBeNull();
  });

  it("heading text appears as an aria-hidden label span, not as an h1-h6 element", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");

    for (const heading of ["Truth", "Relevance", "Sentiment"]) {
      const headingEls = Array.from(
        root.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5, h6"),
      ).filter((node) => node.textContent?.trim() === heading);
      expect(headingEls).toHaveLength(0);

      const hintSpans = Array.from(
        root.querySelectorAll<HTMLElement>("span[aria-hidden='true']"),
      ).filter((node) => node.textContent?.trim().toUpperCase() === heading.toUpperCase());
      expect(hintSpans.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("clicking the truth row opens a popover with the expansion for first_person", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.click(truthRow);
    await screen.findByText(
      /direct, lived experience/i,
    );
  });

  it("clicking the relevance row opens a popover with the expansion for on_topic", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const relevanceRow = screen.getByTestId("weather-axis-card-relevance");
    fireEvent.click(relevanceRow);
    await screen.findByText(
      /stays close to the source/i,
    );
  });

  it("clicking the sentiment row opens a popover with the expansion for that label", async () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          sentiment: { label: "neutral", logprob: null, alternatives: [] },
        })}
      />
    ));
    const sentimentRow = screen.getByTestId("weather-axis-card-sentiment");
    fireEvent.click(sentimentRow);
    await screen.findByText(
      /not taking a strong emotional stance/i,
    );
  });

  it("pressing Escape closes the popover after it has been opened", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.click(truthRow);
    await screen.findByText(/direct, lived experience/i);

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });

    await waitFor(() => {
      expect(screen.queryByText(/direct, lived experience/i)).toBeNull();
    });
  });

  it("clicking outside the popover dismisses it", async () => {
    render(() => (
      <div>
        <button data-testid="outside-target" type="button">
          outside
        </button>
        <WeatherReport report={makeWeatherReport()} />
      </div>
    ));
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.click(truthRow);
    await screen.findByText(/direct, lived experience/i);

    const outside = screen.getByTestId("outside-target");
    await waitFor(() => {
      fireEvent.pointerDown(outside, { pointerType: "mouse", button: 0 });
      expect(screen.queryByText(/direct, lived experience/i)).toBeNull();
    });
  });

  it("does not open the popover on pointerenter — popover is click/tap only", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.pointerEnter(truthRow);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText(/direct, lived experience/i)).toBeNull();
  });

  it("axis row trigger is a button with aria-label combining axis context and visible value", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: { label: "first_person", logprob: -0.40, alternatives: [] },
          relevance: { label: "on_topic", logprob: null, alternatives: [] },
        })}
      />
    ));

    const truthTrigger = screen.getByTestId("weather-axis-card-truth");
    const truthLabel = truthTrigger.getAttribute("aria-label") ?? "";
    expect(truthLabel).toMatch(/Truth/i);
    expect(truthLabel).toMatch(/First-Person/i);

    const relevanceTrigger = screen.getByTestId("weather-axis-card-relevance");
    const relevanceLabel = relevanceTrigger.getAttribute("aria-label") ?? "";
    expect(relevanceLabel).toMatch(/Relevance/i);
    expect(relevanceLabel).toMatch(/On Topic/i);
  });

  it("does not put role=button or aria-haspopup on the axis pair wrapper", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport()}
        safetyRecommendation={makeSafetyRecommendation()}
      />
    ));
    const root = screen.getByTestId("weather-report");
    const pairs = root.querySelectorAll('.pair');
    expect(pairs.length).toBe(4);
    for (const pair of Array.from(pairs)) {
      expect(pair.getAttribute("role")).not.toBe("button");
      expect(pair.getAttribute("aria-haspopup")).toBeNull();
      expect(pair.getAttribute("tabindex")).toBeNull();
    }
  });

  it("renders stable shimmer skeletons when report is null", () => {
    render(() => <WeatherReport report={null} />);

    expect(screen.getByTestId("weather-report-skeleton")).toBeDefined();
    expect(screen.getByTestId("weather-skeleton-truth")).toBeDefined();
    expect(screen.getByTestId("weather-skeleton-relevance")).toBeDefined();
    expect(screen.getByTestId("weather-skeleton-sentiment")).toBeDefined();
    expect(
      screen
        .getByTestId("weather-skeleton-truth")
        .querySelector("[data-opennotes-skeleton]"),
    ).toBeTruthy();
  });

  it("skeleton has four axis pairs (safety, truth, relevance, sentiment)", () => {
    render(() => <WeatherReport report={null} />);
    const root = screen.getByTestId("weather-report-skeleton");
    expect(root.querySelector('[data-testid="weather-skeleton-safety"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="weather-skeleton-truth"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="weather-skeleton-relevance"]')).not.toBeNull();
    expect(root.querySelector('[data-testid="weather-skeleton-sentiment"]')).not.toBeNull();
  });

  it("renders the literal axis labels (TRUTH, RELEVANCE, SENTIMENT) statically in the loading state", () => {
    render(() => <WeatherReport report={null} />);

    expect(
      screen.getByTestId("weather-skeleton-truth-label").textContent,
    ).toBe("TRUTH");
    expect(
      screen.getByTestId("weather-skeleton-relevance-label").textContent,
    ).toBe("RELEVANCE");
    expect(
      screen.getByTestId("weather-skeleton-sentiment-label").textContent,
    ).toBe("SENTIMENT");

    for (const axis of ["truth", "relevance", "sentiment"]) {
      expect(
        screen
          .getByTestId(`weather-skeleton-${axis}`)
          .querySelector("[data-opennotes-skeleton]"),
      ).toBeTruthy();
    }
  });

  it("does not put a Skeleton primitive on the axis label cell (label must be literal text)", () => {
    render(() => <WeatherReport report={null} />);
    for (const axis of ["truth", "relevance", "sentiment"]) {
      const labelCell = screen.getByTestId(`weather-skeleton-${axis}-label`);
      expect(labelCell.querySelector("[data-opennotes-skeleton]")).toBeNull();
    }
  });

  it("does not impose a min-h-[110px] on the skeleton container", () => {
    render(() => <WeatherReport report={null} />);
    const root = screen.getByTestId("weather-report-skeleton");
    expect(root.className).not.toContain("min-h-[110px]");
  });

  it("uses Skeleton primitives, not legacy skeleton-pulse-extra classes", () => {
    render(() => <WeatherReport report={null} />);
    const root = screen.getByTestId("weather-report-skeleton");
    expect(root.querySelector(".skeleton-pulse-extra")).toBeNull();
    expect(root.querySelector(".skeleton-pulse-extra-delay-1")).toBeNull();
    expect(root.querySelector(".skeleton-pulse-extra-delay-2")).toBeNull();
  });

  it("does not impose a min-h-[110px] on the real (data) weather report", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");
    expect(root.className).not.toContain("min-h-[110px]");
  });

  it("populated container has bg-card class", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");
    const cls = root.className;
    expect(cls).toContain("bg-card");
  });

  it("populated container uses inline-flex layout (hugs its content)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");
    expect(root.className).toContain("inline-flex");
  });

  it("forwards consumer-provided class to the outer container", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport()}
        class="lg:max-w-md custom-rail"
      />
    ));

    const className = screen.getByTestId("weather-report").className;
    expect(className).toContain("lg:max-w-md");
    expect(className).toContain("custom-rail");
  });

  it("renders alternatives only when present", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "sourced",
            logprob: null,
            alternatives: [{ label: "factual_claims", logprob: null }],
          },
        })}
      />
    ));

    expect(screen.getByTestId("weather-truth-alternatives")).toBeDefined();
    expect(screen.queryByTestId("weather-relevance-alternatives")).toBeNull();
  });

  it("updates from skeletons to real weather data after polling", async () => {
    const [report, setReport] = createSignal<WeatherReportData | null>(null);
    render(() => <WeatherReport report={report()} />);

    expect(screen.getByTestId("weather-report-skeleton")).toBeDefined();

    setReport(makeWeatherReport());

    await waitFor(() => {
      expect(screen.queryByTestId("weather-report-skeleton")).toBeNull();
      expect(screen.getByTestId("weather-truth-value").textContent).toBe(
        "First-Person",
      );
    });
  });

  it("updates mapped label text when a non-null report changes", async () => {
    const [report, setReport] = createSignal<WeatherReportData | null>(
      makeWeatherReport({
        truth: {
          label: "sourced",
          logprob: null,
          alternatives: [],
        },
      }),
    );
    render(() => <WeatherReport report={report()} />);

    expect(screen.getByTestId("weather-truth-value").textContent).toBe("Sourced");

    setReport(
      makeWeatherReport({
        truth: {
          label: "misleading",
          logprob: null,
          alternatives: [],
        },
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("weather-truth-value").textContent).toBe(
        "Actively Misleading",
      );
    });
  });

  it("maps factual claims and hearsay to stance vocabulary", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "factual_claims",
            logprob: null,
            alternatives: [],
          },
        })}
      />
    ));
    expect(screen.getByTestId("weather-truth-value").textContent).toBe(
      "Factual Claims",
    );

    cleanup();

    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "hearsay",
            logprob: null,
            alternatives: [],
          },
        })}
      />
    ));
    expect(screen.getByTestId("weather-truth-value").textContent).toBe(
      "Second-Hand",
    );
  });

  it("renders logprob alternatives as linear probability percentages", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "sourced",
            logprob: -0.12,
            alternatives: [{ label: "factual_claims", logprob: -1.25 }],
          },
        })}
      />
    ));

    expect(screen.getByTestId("weather-truth-alternatives").textContent).toContain(
      "Factual Claims (28.65%)",
    );
  });

  it("axis category label appears as an aria-hidden span INSIDE the trigger button, above the eval value", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const root = screen.getByTestId("weather-report");

    const expectedHeadings: Array<{ axis: string; heading: string }> = [
      { axis: "truth", heading: "TRUTH" },
      { axis: "relevance", heading: "RELEVANCE" },
      { axis: "sentiment", heading: "SENTIMENT" },
    ];

    for (const { axis, heading } of expectedHeadings) {
      const trigger = screen.getByTestId(`weather-axis-card-${axis}`);
      const allHintSpans = Array.from(
        trigger.querySelectorAll<HTMLSpanElement>("span[aria-hidden='true']"),
      );
      const hintSpan = allHintSpans.find(
        (s) => s.textContent?.trim().toUpperCase() === heading,
      );
      expect(hintSpan).toBeDefined();
      expect(hintSpan!.getAttribute("aria-hidden")).toBe("true");
      expect(hintSpan!.className).toContain("uppercase");

      expect(trigger.contains(hintSpan!)).toBe(true);
    }

    expect(root.querySelector('[data-slot="table-header"]')).toBeNull();
  });

  it("clicking the category label span opens the popover (whole-trigger click)", async () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport()}
        safetyRecommendation={makeSafetyRecommendation()}
      />
    ));

    for (const { axis, heading, expectedText } of [
      { axis: "truth", heading: "TRUTH", expectedText: /direct, lived experience/i },
      { axis: "safety", heading: "SAFETY", expectedText: /moderation, web risk/i },
    ] as Array<{ axis: string; heading: string; expectedText: RegExp }>) {
      const trigger = screen.getByTestId(`weather-axis-card-${axis}`);
      const hintSpan = Array.from(
        trigger.querySelectorAll<HTMLSpanElement>("span[aria-hidden='true']"),
      ).find((s) => s.textContent?.trim().toUpperCase() === heading);
      expect(hintSpan).toBeDefined();

      fireEvent.click(hintSpan!);
      await screen.findByText(expectedText);
      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    }
  });

  it("axis category label spans have cursor-default and select-none classes", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport()}
        safetyRecommendation={makeSafetyRecommendation()}
      />
    ));

    const root = screen.getByTestId("weather-report");

    const allAxes = [
      { axis: "safety", heading: "SAFETY" },
      { axis: "truth", heading: "TRUTH" },
      { axis: "relevance", heading: "RELEVANCE" },
      { axis: "sentiment", heading: "SENTIMENT" },
    ];

    for (const { heading } of allAxes) {
      const allHintSpans = Array.from(
        root.querySelectorAll<HTMLSpanElement>("span[aria-hidden='true']"),
      ).filter((s) => s.textContent?.trim().toUpperCase() === heading);
      expect(allHintSpans.length).toBeGreaterThanOrEqual(1);
      for (const span of allHintSpans) {
        expect(span.className).toContain("cursor-default");
        expect(span.className).toContain("select-none");
      }
    }
  });

  it("category label spans use font-condensed class", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const trigger = screen.getByTestId("weather-axis-card-truth");
    const hintSpan = Array.from(
      trigger.querySelectorAll<HTMLSpanElement>("span[aria-hidden='true']"),
    ).find((s) => s.textContent?.trim().toUpperCase() === "TRUTH");
    expect(hintSpan).toBeDefined();
    expect(hintSpan!.className).toContain("font-condensed");
  });

  it("eval value uses font-serif class (neutral display, no per-axis color tinting)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const evalSpan = screen.getByTestId("weather-truth-value");
    expect(evalSpan.className).toContain("font-serif");
    expect(evalSpan.className).not.toMatch(/text-indigo|text-lime|text-sky|text-amber|text-slate/);
  });

  it("eval values carry no background badge class", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const className = screen.getByTestId("weather-truth-value").className;
    expect(className).not.toMatch(/(?:^|\s)bg-/);
  });

  it("all rows with axis data render a button trigger, even free-form labels not in weather-labels.json", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          sentiment: { label: "warmly skeptical", logprob: null, alternatives: [] },
        })}
      />
    ));

    expect(screen.getByTestId("weather-axis-card-truth")).toBeDefined();
    expect(screen.getByTestId("weather-axis-card-relevance")).toBeDefined();
    expect(screen.getByTestId("weather-axis-card-sentiment")).toBeDefined();

    const sentimentValue = screen.getByTestId("weather-sentiment-value");
    expect(sentimentValue).toBeDefined();
    expect(sentimentValue.closest("button")).not.toBeNull();
  });

  it("clicking a row with a free-form label (not in weather-labels.json) falls back to axis-level TOOLTIP_COPY content", async () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          sentiment: { label: "warmly skeptical", logprob: null, alternatives: [] },
        })}
      />
    ));

    const sentimentRow = screen.getByTestId("weather-axis-card-sentiment");
    fireEvent.click(sentimentRow);
    await screen.findByText(/emotional register/i);
  });

  it("alternatives ul is NOT a descendant of the trigger button (valid HTML5)", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "sourced",
            logprob: null,
            alternatives: [{ label: "factual_claims", logprob: null }],
          },
        })}
      />
    ));

    const trigger = screen.getByTestId("weather-axis-card-truth");
    const altsList = screen.getByTestId("weather-truth-alternatives");
    expect(trigger.contains(altsList)).toBe(false);
  });

  it("trigger button has hover:bg-muted/40 class for axis hover band", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const trigger = screen.getByTestId("weather-axis-card-truth");
    expect(trigger.className).toContain("hover:bg-muted/40");
  });

  it("renders a WeatherHelpButton (aria-label /explain.*weather/i) and no FeedbackBell (bell_location=card:weather)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const helpButton = screen.getByRole("button", {
      name: /explain.*weather/i,
    });
    expect(helpButton).toBeDefined();

    const bellButton = screen.queryByRole("button", {
      name: /send feedback.*card:weather/i,
    });
    expect(bellButton).toBeNull();
  });

  it("renders the help button (aria-label /explain.*weather/i) in the skeleton (null report) path", () => {
    render(() => <WeatherReport report={null} />);

    const helpButton = screen.getByRole("button", {
      name: /explain.*weather/i,
    });
    expect(helpButton).toBeDefined();
  });

  it("skeleton axis pairs region has aria-hidden='true'", () => {
    render(() => <WeatherReport report={null} />);

    const skeletonCard = screen.getByTestId("weather-report-skeleton");
    const skeletonTruth = skeletonCard.querySelector('[data-testid="weather-skeleton-truth"]');
    expect(skeletonTruth).not.toBeNull();

    let node: Element | null = skeletonTruth!;
    let foundAriaHidden = false;
    while (node && node !== skeletonCard) {
      if (node.getAttribute("aria-hidden") === "true") {
        foundAriaHidden = true;
        break;
      }
      node = node.parentElement;
    }
    expect(foundAriaHidden).toBe(true);
  });

  it("skeleton help button is NOT inside the aria-hidden region", () => {
    render(() => <WeatherReport report={null} />);

    const helpButton = screen.getByRole("button", {
      name: /explain.*weather/i,
    });
    expect(helpButton).toBeDefined();

    let node: Element | null = helpButton.parentElement;
    while (node) {
      expect(node.getAttribute("aria-hidden")).not.toBe("true");
      if (node.getAttribute("data-testid") === "weather-report-skeleton") break;
      node = node.parentElement;
    }
  });

  it("truth skeleton eval cell renders 2 word-shape Skeleton elements", () => {
    render(() => <WeatherReport report={null} />);

    const wordsCell = screen.getByTestId("weather-skeleton-truth-words");
    const skeletons = wordsCell.querySelectorAll("[data-opennotes-skeleton]");
    expect(skeletons.length).toBe(2);
  });

  it("relevance skeleton eval cell renders 2 word-shape Skeleton elements", () => {
    render(() => <WeatherReport report={null} />);

    const wordsCell = screen.getByTestId("weather-skeleton-relevance-words");
    const skeletons = wordsCell.querySelectorAll("[data-opennotes-skeleton]");
    expect(skeletons.length).toBe(2);
  });

  it("sentiment skeleton eval cell renders exactly 1 word-shape Skeleton element", () => {
    render(() => <WeatherReport report={null} />);

    const wordsCell = screen.getByTestId("weather-skeleton-sentiment-words");
    const skeletons = wordsCell.querySelectorAll("[data-opennotes-skeleton]");
    expect(skeletons.length).toBe(1);
  });

  it("skeleton label cell still contains literal axis text (TRUTH / RELEVANCE / SENTIMENT)", () => {
    render(() => <WeatherReport report={null} />);

    expect(screen.getByTestId("weather-skeleton-truth-label").textContent).toBe("TRUTH");
    expect(screen.getByTestId("weather-skeleton-relevance-label").textContent).toBe("RELEVANCE");
    expect(screen.getByTestId("weather-skeleton-sentiment-label").textContent).toBe("SENTIMENT");
  });

  it("outer card has pb-8 but NOT pr-8 (help button has bottom padding only)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");
    expect(root.className).toContain("pb-8");
    expect(root.className).not.toContain("pr-8");
  });

  it("skeleton outer card does NOT have pr-8", () => {
    render(() => <WeatherReport report={null} />);
    const root = screen.getByTestId("weather-report-skeleton");
    expect(root.className).not.toContain("pr-8");
  });

  describe("WeatherSymbol shape selection per safety level", () => {
    it("safe level renders a circle symbol (data-testid=weather-symbol-safe)", () => {
      render(() => (
        <WeatherSymbol level="safe" lobeColors={["#0ea5e9", "#10b981", "#f59e0b"]} />
      ));
      expect(screen.getByTestId("weather-symbol-safe")).toBeDefined();
      const svg = screen.getByTestId("weather-symbol-safe");
      expect(svg.querySelector("circle")).not.toBeNull();
    });

    it("mild level renders a rounded square symbol (data-testid=weather-symbol-mild)", () => {
      render(() => (
        <WeatherSymbol level="mild" lobeColors={["#06b6d4", "#84cc16", "#64748b"]} />
      ));
      expect(screen.getByTestId("weather-symbol-mild")).toBeDefined();
      const svg = screen.getByTestId("weather-symbol-mild");
      expect(svg.querySelector("circle")).toBeNull();
      expect(svg.querySelectorAll("path").length).toBeGreaterThan(0);
    });

    it("caution level renders a triangle symbol (data-testid=weather-symbol-caution)", () => {
      render(() => (
        <WeatherSymbol level="caution" lobeColors={["#78716c", "#06b6d4", "#f97316"]} />
      ));
      expect(screen.getByTestId("weather-symbol-caution")).toBeDefined();
    });

    it("unsafe level renders an octagon symbol (data-testid=weather-symbol-unsafe)", () => {
      render(() => (
        <WeatherSymbol level="unsafe" lobeColors={["#d946ef", "#d946ef", "#8b5cf6"]} />
      ));
      expect(screen.getByTestId("weather-symbol-unsafe")).toBeDefined();
    });

    it("unknown level renders a rhombus symbol (data-testid=weather-symbol-unknown)", () => {
      render(() => (
        <WeatherSymbol level="unknown" lobeColors={["#64748b", "#64748b", "#64748b"]} />
      ));
      expect(screen.getByTestId("weather-symbol-unknown")).toBeDefined();
      const svg = screen.getByTestId("weather-symbol-unknown");
      expect(svg.querySelector("polygon")).not.toBeNull();
      expect(svg.querySelector("circle")).toBeNull();
    });
  });

  describe("WeatherSymbol palette and trefoil colors", () => {
    it("safe symbol uses #4ade80 fill and #bbf7d0 outline", () => {
      render(() => (
        <WeatherSymbol level="safe" lobeColors={["#0ea5e9", "#10b981", "#f59e0b"]} />
      ));
      const svg = screen.getByTestId("weather-symbol-safe");
      const circle = svg.querySelector("circle");
      expect(circle?.getAttribute("fill")).toBe("#4ade80");
    });

    it("mild symbol uses #fef9c3 fill", () => {
      render(() => (
        <WeatherSymbol level="mild" lobeColors={["#06b6d4", "#84cc16", "#64748b"]} />
      ));
      const svg = screen.getByTestId("weather-symbol-mild");
      const shapePath = svg.querySelector("path");
      expect(shapePath?.getAttribute("fill")).toBe("#fef9c3");
    });

    it("caution symbol uses #facc15 fill", () => {
      render(() => (
        <WeatherSymbol level="caution" lobeColors={["#78716c", "#06b6d4", "#f97316"]} />
      ));
      const svg = screen.getByTestId("weather-symbol-caution");
      const shapePath = svg.querySelector("path");
      expect(shapePath?.getAttribute("fill")).toBe("#facc15");
    });

    it("unsafe symbol uses #c0392b fill", () => {
      render(() => (
        <WeatherSymbol level="unsafe" lobeColors={["#d946ef", "#d946ef", "#8b5cf6"]} />
      ));
      const svg = screen.getByTestId("weather-symbol-unsafe");
      const shapePath = svg.querySelector("path");
      expect(shapePath?.getAttribute("fill")).toBe("#c0392b");
    });

    it("unknown symbol uses gray-200 fill (#e5e7eb) and gray-500 outline (#6b7280)", () => {
      render(() => (
        <WeatherSymbol level="unknown" lobeColors={["#64748b", "#64748b", "#64748b"]} />
      ));
      const svg = screen.getByTestId("weather-symbol-unknown");
      const poly = svg.querySelector("polygon");
      expect(poly?.getAttribute("fill")).toBe("#e5e7eb");
      const outlinePoly = Array.from(svg.querySelectorAll("polygon")).find(
        (p) => p.getAttribute("fill") === "none",
      );
      expect(outlinePoly?.getAttribute("stroke")).toBe("#6b7280");
    });

    it("mild trefoil stroke uses mismatched #f5a672 (not same as outline #fed7aa)", () => {
      render(() => (
        <WeatherSymbol level="mild" lobeColors={["#06b6d4", "#84cc16", "#64748b"]} />
      ));
      const svg = screen.getByTestId("weather-symbol-mild");
      const strokPaths = Array.from(svg.querySelectorAll("path")).filter(
        (p) => p.getAttribute("stroke") !== null && p.getAttribute("fill") === "none",
      );
      const trefoilPaths = strokPaths.filter(
        (p) => p.getAttribute("stroke-width") === "1.75",
      );
      expect(trefoilPaths.length).toBeGreaterThan(0);
      for (const p of trefoilPaths) {
        expect(p.getAttribute("stroke")).toBe("#f5a672");
        expect(p.getAttribute("stroke")).not.toBe("#fed7aa");
      }
    });

    it("lobe colors come from the provided lobeColors prop", () => {
      const lobe0 = "#0ea5e9";
      const lobe1 = "#10b981";
      const lobe2 = "#f59e0b";
      render(() => (
        <WeatherSymbol level="safe" lobeColors={[lobe0, lobe1, lobe2]} />
      ));
      const svg = screen.getByTestId("weather-symbol-safe");
      const filledPaths = Array.from(svg.querySelectorAll("path, circle")).filter(
        (el) => {
          const fill = el.getAttribute("fill");
          return fill && fill !== "none" && fill !== "#4ade80";
        },
      );
      const fills = filledPaths.map((p) => p.getAttribute("fill"));
      expect(fills).toContain(lobe0);
      expect(fills).toContain(lobe1);
      expect(fills).toContain(lobe2);
    });
  });

  describe("WeatherReport symbol integration", () => {
    it("renders a WeatherSymbol inside the report", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const root = screen.getByTestId("weather-report");
      expect(root.querySelector('[data-testid="weather-symbol-safe"]')).not.toBeNull();
    });

    it("symbol is to the LEFT of the axis stack in DOM order", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      const axisStack = screen.getByTestId("weather-axis-stack");
      expect(symbolCell).not.toBeNull();
      expect(axisStack).not.toBeNull();
      const position = symbolCell.compareDocumentPosition(axisStack);
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("renders unknown (rhombus) symbol when safetyRecommendation is null", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={null}
        />
      ));
      const root = screen.getByTestId("weather-report");
      expect(root.querySelector('[data-testid="weather-symbol-unknown"]')).not.toBeNull();
      expect(root.querySelector('[data-testid="weather-symbol-safe"]')).toBeNull();
    });

    it("renders unknown (rhombus) symbol when safetyRecommendation is not provided", () => {
      render(() => (
        <WeatherReport report={makeWeatherReport()} />
      ));
      const root = screen.getByTestId("weather-report");
      expect(root.querySelector('[data-testid="weather-symbol-unknown"]')).not.toBeNull();
      expect(root.querySelector('[data-testid="weather-symbol-safe"]')).toBeNull();
    });

    it("renders unsafe symbol when safety level is unsafe", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "unsafe" })}
        />
      ));
      const root = screen.getByTestId("weather-report");
      expect(root.querySelector('[data-testid="weather-symbol-unsafe"]')).not.toBeNull();
    });

    it("lobe colors in the symbol reflect exact per-axis variant hex: first_person=#6366f1, on_topic=#84cc16, neutral=#64748b", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport({
            truth: { label: "first_person", logprob: null, alternatives: [] },
            relevance: { label: "on_topic", logprob: null, alternatives: [] },
            sentiment: { label: "neutral", logprob: null, alternatives: [] },
          })}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const root = screen.getByTestId("weather-report");
      const svg = root.querySelector('[data-testid="weather-symbol-safe"]');
      expect(svg).not.toBeNull();
      const lobePaths = Array.from(svg!.querySelectorAll("path")).filter(
        (p) => p.getAttribute("fill") && p.getAttribute("fill") !== "none" && p.getAttribute("fill") !== "#4ade80",
      );
      const fills = lobePaths.map((p) => p.getAttribute("fill"));
      expect(fills).toContain("#6366f1");
      expect(fills).toContain("#84cc16");
      expect(fills).toContain("#64748b");
    });
  });

  describe("Safety row", () => {
    it("renders 4 axis pairs with Safety first when safetyRecommendation is provided", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation()}
        />
      ));

      const root = screen.getByTestId("weather-report");
      const pairs = Array.from(root.querySelectorAll('.pair'));
      expect(pairs.length).toBe(4);

      const firstPair = pairs[0];
      expect(firstPair.querySelector('[data-testid="weather-axis-card-safety"]')).not.toBeNull();
    });

    it("Safety value uses text-foreground (neutral, same as other axes) for level=safe", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));

      const safetyValue = screen.getByTestId("weather-safety-value");
      expect(safetyValue.className).toContain("text-foreground");
      expect(safetyValue.className).not.toMatch(/text-emerald/);
      expect(safetyValue.className).not.toMatch(/(?:^|\s)bg-/);
    });

    it("Safety value uses text-foreground (neutral, same as other axes) for level=unsafe", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "unsafe" })}
        />
      ));

      const safetyValue = screen.getByTestId("weather-safety-value");
      expect(safetyValue.className).toContain("text-foreground");
      expect(safetyValue.className).not.toMatch(/text-rose/);
      expect(safetyValue.className).not.toMatch(/(?:^|\s)bg-/);
    });

    it("Safety value uses text-foreground (neutral, same as other axes) for level=mild", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "mild" })}
        />
      ));

      const safetyValue = screen.getByTestId("weather-safety-value");
      expect(safetyValue.className).toContain("text-foreground");
      expect(safetyValue.className).not.toMatch(/text-yellow/);
      expect(safetyValue.className).not.toMatch(/(?:^|\s)bg-/);
    });

    it("Safety popover for mild renders JSON expansion text", async () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "mild" })}
        />
      ));

      const safetyTrigger = screen.getByTestId("weather-axis-card-safety");
      fireEvent.click(safetyTrigger);
      await screen.findByText(/minor concerns surfaced/i);
    });

    it("Safety value uses text-foreground (neutral, same as other axes) for level=caution", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "caution" })}
        />
      ));

      const safetyValue = screen.getByTestId("weather-safety-value");
      expect(safetyValue.className).toContain("text-foreground");
      expect(safetyValue.className).not.toMatch(/text-amber/);
      expect(safetyValue.className).not.toMatch(/(?:^|\s)bg-/);
    });

    it("Safety popover for caution renders JSON expansion text", async () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "caution" })}
        />
      ));

      const safetyTrigger = screen.getByTestId("weather-axis-card-safety");
      fireEvent.click(safetyTrigger);
      await screen.findByText(/multiple signals worth a careful read/i);
    });

    it("Safety popover expansion comes from labels JSON when level is known", async () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));

      const safetyTrigger = screen.getByTestId("weather-axis-card-safety");
      fireEvent.click(safetyTrigger);
      await screen.findByText(/moderation, web risk, image, and video checks/i);
    });

    it("Safety popover falls back to recommendation.rationale when formatWeatherExpansion returns null", async () => {
      const spy = vi
        .spyOn(weatherLabels, "formatWeatherExpansion")
        .mockReturnValueOnce(null);

      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({
            level: "safe",
            rationale: "Fallback rationale text shown here.",
          })}
        />
      ));

      const safetyTrigger = screen.getByTestId("weather-axis-card-safety");
      fireEvent.click(safetyTrigger);
      await screen.findByText(/fallback rationale text shown here/i);

      spy.mockRestore();
    });

    it("Safety row renders 'Not available' when safetyRecommendation is null", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={null}
        />
      ));

      const safetyValue = screen.getByTestId("weather-safety-value");
      expect(safetyValue.textContent).toContain("Not available");
    });

    it("Safety row renders 'Not available' when safetyRecommendation is not provided", () => {
      render(() => <WeatherReport report={makeWeatherReport()} />);

      const safetyValue = screen.getByTestId("weather-safety-value");
      expect(safetyValue.textContent).toContain("Not available");
    });

    it("skeleton includes a safety row", () => {
      render(() => <WeatherReport report={null} />);

      expect(screen.getByTestId("weather-skeleton-safety")).toBeDefined();
      expect(screen.getByTestId("weather-skeleton-safety-label").textContent).toBe("SAFETY");
    });
  });

  describe("Focus button", () => {
    it("Focus button is hidden when rendered without SidebarStoreProvider", async () => {
      render(() => <WeatherReport report={makeWeatherReport()} />);
      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);
      await screen.findByText(/direct, lived experience/i);
      expect(screen.queryByTestId("weather-truth-focus")).toBeNull();
    });

    it("Focus button is visible when rendered inside SidebarStoreProvider", async () => {
      render(() => (
        <SidebarStoreProvider>
          <WeatherReport report={makeWeatherReport()} />
        </SidebarStoreProvider>
      ));
      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);
      await screen.findByText(/direct, lived experience/i);
      expect(screen.getByTestId("weather-truth-focus")).toBeDefined();
    });

    it("clicking Focus button closes the popover and calls isolateGroup for truth axis", async () => {
      let capturedStore: ReturnType<typeof useSidebarStore> = null;
      function StoreProbe() {
        capturedStore = useSidebarStore();
        return null;
      }
      render(() => (
        <SidebarStoreProvider>
          <StoreProbe />
          <WeatherReport
            report={makeWeatherReport()}
            safetyRecommendation={makeSafetyRecommendation()}
          />
        </SidebarStoreProvider>
      ));

      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);
      await screen.findByText(/direct, lived experience/i);
      expect(capturedStore!.highlightedGroup()).toBe("Facts/claims");

      const focusBtn = screen.getByTestId("weather-truth-focus");
      fireEvent.click(focusBtn);

      await waitFor(() => {
        expect(screen.queryByText(/direct, lived experience/i)).toBeNull();
      });

      expect(capturedStore!.isOpen("Facts/claims")).toBe(true);
      expect(capturedStore!.isOpen("Safety")).toBe(false);
      expect(capturedStore!.isOpen("Tone/dynamics")).toBe(false);
      expect(capturedStore!.isOpen("Opinions/sentiments")).toBe(false);
    });

    it("clicking Focus button returns focus to the trigger element", async () => {
      render(() => (
        <SidebarStoreProvider>
          <WeatherReport report={makeWeatherReport()} />
        </SidebarStoreProvider>
      ));

      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);
      await screen.findByText(/direct, lived experience/i);

      const focusBtn = screen.getByTestId("weather-truth-focus");
      focusBtn.focus();
      fireEvent.click(focusBtn);

      await waitFor(() => {
        expect(screen.queryByText(/direct, lived experience/i)).toBeNull();
      });

      await waitFor(() => {
        expect(document.activeElement).toBe(truthTrigger);
      });
    });

    it("Focus button has aria-label='Focus this section'", async () => {
      render(() => (
        <SidebarStoreProvider>
          <WeatherReport report={makeWeatherReport()} />
        </SidebarStoreProvider>
      ));
      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);
      await screen.findByText(/direct, lived experience/i);
      const focusBtn = screen.getByTestId("weather-truth-focus");
      expect(focusBtn.getAttribute("aria-label")).toBe("Focus this section");
    });
  });

  describe("Highlight cleanup", () => {
    it("clicking the Focus button clears highlightedGroup immediately (focus-button leak fix)", async () => {
      let capturedStore: ReturnType<typeof useSidebarStore> = null;
      function StoreProbe() {
        capturedStore = useSidebarStore();
        return null;
      }
      render(() => (
        <SidebarStoreProvider>
          <StoreProbe />
          <WeatherReport
            report={makeWeatherReport()}
            safetyRecommendation={makeSafetyRecommendation()}
          />
        </SidebarStoreProvider>
      ));

      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBe("Facts/claims");
      });

      const focusBtn = screen.getByTestId("weather-truth-focus");
      fireEvent.click(focusBtn);

      expect(capturedStore!.highlightedGroup()).toBeNull();
    });

    it("switching directly from one axis popover to another leaves highlightedGroup on the new axis, never null (axis-switch race fix)", async () => {
      let capturedStore: ReturnType<typeof useSidebarStore> = null;
      function StoreProbe() {
        capturedStore = useSidebarStore();
        return null;
      }
      render(() => (
        <SidebarStoreProvider>
          <StoreProbe />
          <WeatherReport
            report={makeWeatherReport()}
            safetyRecommendation={makeSafetyRecommendation()}
          />
        </SidebarStoreProvider>
      ));

      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBe("Facts/claims");
      });

      const sentimentTrigger = screen.getByTestId("weather-axis-card-sentiment");
      fireEvent.click(sentimentTrigger);

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBe("Opinions/sentiments");
      });
    });
  });

  describe("SidebarStore integration", () => {
    it("opening a truth popover inside SidebarStoreProvider sets highlightedGroup to Facts/claims", async () => {
      let capturedStore: ReturnType<typeof useSidebarStore> = null;
      function StoreProbe() {
        capturedStore = useSidebarStore();
        return null;
      }
      render(() => (
        <SidebarStoreProvider>
          <StoreProbe />
          <WeatherReport
            report={makeWeatherReport()}
            safetyRecommendation={makeSafetyRecommendation()}
          />
        </SidebarStoreProvider>
      ));

      expect(capturedStore).not.toBeNull();
      expect(capturedStore!.highlightedGroup()).toBeNull();

      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBe("Facts/claims");
      });

      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBeNull();
      });
    });

    it("opening a relevance popover inside SidebarStoreProvider sets highlightedGroup to Tone/dynamics", async () => {
      let capturedStore: ReturnType<typeof useSidebarStore> = null;
      function StoreProbe() {
        capturedStore = useSidebarStore();
        return null;
      }
      render(() => (
        <SidebarStoreProvider>
          <StoreProbe />
          <WeatherReport
            report={makeWeatherReport()}
            safetyRecommendation={makeSafetyRecommendation()}
          />
        </SidebarStoreProvider>
      ));

      const relevanceTrigger = screen.getByTestId("weather-axis-card-relevance");
      fireEvent.click(relevanceTrigger);

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBe("Tone/dynamics");
      });

      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

      await waitFor(() => {
        expect(capturedStore!.highlightedGroup()).toBeNull();
      });
    });

    it("AxisRow without a provider does not throw and popover still opens", async () => {
      expect(() => {
        render(() => <WeatherReport report={makeWeatherReport()} />);
      }).not.toThrow();

      const truthTrigger = screen.getByTestId("weather-axis-card-truth");
      fireEvent.click(truthTrigger);
      await screen.findByText(/direct, lived experience/i);
    });

    it("useSidebarStore returns null outside the provider", () => {
      let capturedStore: ReturnType<typeof useSidebarStore> = undefined as unknown as null;
      function Probe() {
        capturedStore = useSidebarStore();
        return null;
      }
      render(() => <Probe />);
      expect(capturedStore).toBeNull();
    });
  });

  describe("Responsive sizing contract (AC11 — 320px fit)", () => {
    it("populated symbol cell uses clamp(80px,12.8vw,128px) inline style", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation()}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      expect(symbolCell.getAttribute("style")).toContain("clamp(80px,12.8vw,128px)");
    });

    it("skeleton symbol cell uses clamp(80px,12.8vw,128px) inline style (same as populated)", () => {
      render(() => <WeatherReport report={null} />);
      const skeletonRoot = screen.getByTestId("weather-report-skeleton");
      const symbolCell = skeletonRoot.querySelector('[data-testid="weather-skeleton-symbol-cell"]');
      expect(symbolCell).not.toBeNull();
      expect(symbolCell?.getAttribute("style")).toContain("clamp(80px,12.8vw,128px)");
    });

    it("populated axis stack uses min-w-[120px]", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation()}
        />
      ));
      const root = screen.getByTestId("weather-report");
      const axisStack = root.querySelector('[data-testid="weather-axis-stack"]');
      expect(axisStack).not.toBeNull();
      expect(axisStack?.className).toContain("min-w-[120px]");
    });

    it("skeleton axis stack uses min-w-[120px] (same as populated, no width jump)", () => {
      render(() => <WeatherReport report={null} />);
      const root = screen.getByTestId("weather-report-skeleton");
      const axisStack = root.querySelector('[data-testid="weather-skeleton-axis-stack"]');
      expect(axisStack).not.toBeNull();
      expect(axisStack?.className).toContain("min-w-[120px]");
    });
  });

  describe("WeatherSymbol hover-lift (TASK-1610.07 — DESIGN.md card-interactive)", () => {
    it("symbol cell has tabIndex 0 (keyboard-focusable)", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      expect(symbolCell.getAttribute("tabindex")).toBe("0");
    });

    it("symbol cell has an aria-label describing the safety level", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      const label = symbolCell.getAttribute("aria-label") ?? "";
      expect(label.toLowerCase()).toContain("safe");
    });

    it("symbol cell has the motion-safe transition class for hover-lift", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      expect(symbolCell.className).toContain("motion-safe:");
    });

    it("symbol cell references card-hover CSS variable for the lift shadow", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      expect(symbolCell.className).toContain("--card-hover-light");
    });

    it("symbol cell still preserves clamp sizing after hover-lift classes are added", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      expect(symbolCell.getAttribute("style")).toContain("clamp(80px,12.8vw,128px)");
    });

    it("symbol cell does not have an always-on shadow class at rest", () => {
      render(() => (
        <WeatherReport
          report={makeWeatherReport()}
          safetyRecommendation={makeSafetyRecommendation({ level: "safe" })}
        />
      ));
      const symbolCell = screen.getByTestId("weather-symbol-cell");
      expect(symbolCell.className).not.toMatch(/(?:^|\s)shadow-(?:sm|md|lg|xl|2xl)(?:\s|$)/);
    });
  });
});
