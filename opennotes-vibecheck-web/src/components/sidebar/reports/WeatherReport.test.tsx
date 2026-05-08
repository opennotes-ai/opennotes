import { createSignal } from "solid-js";
import { afterEach, describe, expect, it } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import WeatherReport from "./WeatherReport";

type WeatherReportData = components["schemas"]["WeatherReport"];

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

  it("uses Table primitive with three TableRows in TableBody and no TableHeader", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const root = screen.getByTestId("weather-report");
    const tbody = root.querySelector('[data-slot="table-body"]');
    expect(tbody).not.toBeNull();
    const rows = tbody!.querySelectorAll('[data-slot="table-row"]');
    expect(rows.length).toBe(3);
    expect(root.querySelector('[data-slot="table-header"]')).toBeNull();
  });

  it("heading text appears as a right-side hint span that is aria-hidden, not as an h1-h6 element", () => {
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
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const expected: Array<{ axis: string; value: string }> = [
      { axis: "Truth", value: "First-Person" },
      { axis: "Relevance", value: "On Topic" },
    ];
    for (const { axis, value } of expected) {
      const trigger = screen.getByTestId(
        `weather-axis-card-${axis.toLowerCase()}`,
      );
      expect(trigger).toBeDefined();
      const ariaLabel = trigger.getAttribute("aria-label") ?? "";
      expect(ariaLabel).toMatch(new RegExp(axis, "i"));
      expect(ariaLabel).toMatch(new RegExp(value, "i"));
    }
  });

  it("does not put role=button or aria-haspopup on the underlying TableRow", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");
    const rows = root.querySelectorAll('[data-slot="table-row"]');
    expect(rows.length).toBe(3);
    for (const row of Array.from(rows)) {
      expect(row.getAttribute("role")).not.toBe("button");
      expect(row.getAttribute("aria-haspopup")).toBeNull();
      expect(row.getAttribute("tabindex")).toBeNull();
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

  it("skeleton uses the unified Card+Table shape", () => {
    render(() => <WeatherReport report={null} />);
    const root = screen.getByTestId("weather-report-skeleton");
    const tbody = root.querySelector('[data-slot="table-body"]');
    expect(tbody).not.toBeNull();
    const rows = tbody!.querySelectorAll('[data-slot="table-row"]');
    expect(rows.length).toBe(3);
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

  it("populated container keeps Card-style chrome (bg-card)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");
    const cls = root.className;
    expect(cls).toContain("bg-card");
    expect(cls).toContain("rounded-md");
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

  it("renders logprob metadata as linear probability percentages", () => {
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

    expect(screen.getByTestId("weather-truth-confidence").textContent).toBe(
      "88.69%",
    );
    expect(screen.getByTestId("weather-truth-alternatives").textContent).toContain(
      "Factual Claims (28.65%)",
    );
  });

  it("axis heading appears on the RIGHT as an aria-hidden hint span in each row that has a button trigger", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const root = screen.getByTestId("weather-report");

    const expectedHeadings: Array<{ axis: string; heading: string }> = [
      { axis: "truth", heading: "TRUTH" },
      { axis: "relevance", heading: "RELEVANCE" },
    ];

    for (const { axis, heading } of expectedHeadings) {
      const trigger = screen.getByTestId(`weather-axis-card-${axis}`);
      const hintSpans = Array.from(
        trigger.querySelectorAll<HTMLSpanElement>("span[aria-hidden='true']"),
      );
      const hintSpan = hintSpans.find(
        (s) => s.textContent?.trim().toUpperCase() === heading,
      );
      expect(hintSpan).toBeDefined();
      expect(hintSpan!.getAttribute("aria-hidden")).toBe("true");
      expect(hintSpan!.className).toContain("uppercase");
      expect(hintSpan!.className).toContain("tracking-[0.06em]");
      expect(hintSpan!.className).toContain("text-muted-foreground");
      expect(hintSpan!.className).toContain("text-xs");
    }

    const cells = root.querySelectorAll('[data-slot="table-cell"]');
    for (const cell of Array.from(cells)) {
      expect(cell.getAttribute("aria-hidden")).toBeNull();
    }
  });

  it("eval label uses font-condensed; axis hint span does not", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const evalSpan = screen.getByTestId("weather-truth-value");
    expect(evalSpan.className).toContain("font-condensed");

    const trigger = screen.getByTestId("weather-axis-card-truth");
    const hintSpans = Array.from(
      trigger.querySelectorAll<HTMLSpanElement>("span[aria-hidden='true']"),
    );
    for (const hint of hintSpans) {
      expect(hint.className).not.toContain("font-condensed");
    }
  });

  it("eval label has no background badge class (badge background dropped)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const className = screen.getByTestId("weather-truth-value").className;
    expect(className).not.toMatch(/(?:^|\s)bg-/);
  });

  it("renders confidence at text-xs (no arbitrary text-[11px])", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "sourced",
            logprob: -0.12,
            alternatives: [],
          },
        })}
      />
    ));

    const confidence = screen.getByTestId("weather-truth-confidence");
    expect(confidence.className).toContain("text-xs");
    expect(confidence.className).not.toContain("text-[11px]");
  });

  it("renders alternative chips at text-xs (no arbitrary text-[10px])", () => {
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

    const list = screen.getByTestId("weather-truth-alternatives");
    const item = list.querySelector("li");
    expect(item).not.toBeNull();
    expect(item!.className).toContain("text-xs");
    expect(item!.className).not.toContain("text-[10px]");
  });

  it("rows with a known expansion label render a button trigger; rows with unknown label render no button", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          sentiment: { label: "warmly skeptical", logprob: null, alternatives: [] },
        })}
      />
    ));

    expect(screen.getByTestId("weather-axis-card-truth")).toBeDefined();
    expect(screen.getByTestId("weather-axis-card-relevance")).toBeDefined();
    expect(screen.queryByTestId("weather-axis-card-sentiment")).toBeNull();

    const sentimentValue = screen.getByTestId("weather-sentiment-value");
    expect(sentimentValue).toBeDefined();
    expect(sentimentValue.closest("button")).toBeNull();
  });

  it("trigger button has hover:bg-muted/40 class for whole-row hover band", () => {
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

  it("skeleton CardContent wrapping placeholder rows has aria-hidden='true'", () => {
    render(() => <WeatherReport report={null} />);

    const skeletonCard = screen.getByTestId("weather-report-skeleton");
    const tbody = skeletonCard.querySelector('[data-slot="table-body"]');
    expect(tbody).not.toBeNull();

    let node: Element | null = tbody!;
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

  it("skeleton eval cell (words) is LEFT of label cell in DOM order", () => {
    render(() => <WeatherReport report={null} />);

    const truthRow = screen.getByTestId("weather-skeleton-truth");
    const cells = truthRow.querySelectorAll('[data-slot="table-cell"]');
    expect(cells.length).toBe(2);
    const firstCellWordsWrapper = cells[0].querySelector("[data-testid='weather-skeleton-truth-words']");
    expect(firstCellWordsWrapper).not.toBeNull();
    const secondCellLabel = cells[1].getAttribute("data-testid");
    expect(secondCellLabel).toBe("weather-skeleton-truth-label");
  });
});
