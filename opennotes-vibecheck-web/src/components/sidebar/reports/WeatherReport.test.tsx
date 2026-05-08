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
    expect(screen.getByTestId("weather-axis-card-sentiment")).toBeDefined();
    expect(screen.getByTestId("weather-truth-value").textContent).toBe(
      "First-Person",
    );
    expect(screen.getByTestId("weather-relevance-value").textContent).toBe(
      "On Topic",
    );
    expect(screen.getByTestId("weather-sentiment-value").textContent).toBe(
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
    expect(
      root.contains(screen.getByTestId("weather-axis-card-sentiment")),
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

  it("removes inline axis heading text from the row chrome", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const root = screen.getByTestId("weather-report");

    for (const heading of ["Truth", "Relevance", "Sentiment"]) {
      const matches = Array.from(
        root.querySelectorAll<HTMLElement>("h1, h2, h3, h4, h5, h6"),
      ).filter((node) => node.textContent?.trim() === heading);
      expect(matches).toHaveLength(0);
    }
  });

  it("clicking the truth row opens a popover with Option A truth copy (epistemic stance, not verdict)", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.click(truthRow);
    await screen.findByText(
      /Truth — Epistemic stance, not verdict\. Whether claims are sourced, first-person, second-hand, or actively misleading — how the knowledge is held, regardless of whether it's ultimately right\./,
    );
  });

  it("clicking the relevance row opens a popover with Option A relevance copy (tethered to source)", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const relevanceRow = screen.getByTestId("weather-axis-card-relevance");
    fireEvent.click(relevanceRow);
    await screen.findByText(
      /Relevance — How tightly the discussion is tethered to the source\. Insightful engagement, on-topic chatter, drift, or full topic abandonment\./,
    );
  });

  it("clicking the sentiment row opens a popover with Option A sentiment copy (emotional register)", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const sentimentRow = screen.getByTestId("weather-axis-card-sentiment");
    fireEvent.click(sentimentRow);
    await screen.findByText(
      /Sentiment — The emotional register of the conversation\. Read alongside the other axes; tone alone doesn't tell you much\./,
    );
  });

  it("pressing Escape closes the popover after it has been opened", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.click(truthRow);
    await screen.findByText(/Truth — Epistemic stance/);

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });

    await waitFor(() => {
      expect(screen.queryByText(/Truth — Epistemic stance/)).toBeNull();
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
    await screen.findByText(/Truth — Epistemic stance/);

    const outside = screen.getByTestId("outside-target");
    await waitFor(() => {
      fireEvent.pointerDown(outside, { pointerType: "mouse", button: 0 });
      expect(screen.queryByText(/Truth — Epistemic stance/)).toBeNull();
    });
  });

  it("does not open the popover on pointerenter — popover is click/tap only", async () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);
    const truthRow = screen.getByTestId("weather-axis-card-truth");
    fireEvent.pointerEnter(truthRow);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText(/Truth — Epistemic stance/)).toBeNull();
  });

  it("axis row trigger is a button whose accessible name combines axis context and visible value", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const expected: Array<{ axis: string; value: string }> = [
      { axis: "Truth", value: "First-Person" },
      { axis: "Relevance", value: "On Topic" },
      { axis: "Sentiment", value: "Warmly Skeptical" },
    ];
    for (const { axis, value } of expected) {
      const trigger = screen.getByRole("button", {
        name: new RegExp(`${axis}.*${value}`, "i"),
      });
      expect(trigger).toBeDefined();
      expect(trigger.getAttribute("data-testid")).toMatch(
        new RegExp(`^weather-axis-card-${axis.toLowerCase()}$`),
      );
      expect(trigger.getAttribute("aria-label")).toBeNull();
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

  it("renders first-person truth in indigo, not amber or destructive", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const className = screen.getByTestId("weather-truth-value").className;
    expect(className).toContain("text-indigo-700");
    expect(className).not.toContain("amber");
    expect(className).not.toContain("destructive");
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

  it("renders a spaced-caps heading cell per row that is exposed to assistive tech", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const root = screen.getByTestId("weather-report");
    const rows = root.querySelectorAll('[data-slot="table-row"]');
    expect(rows.length).toBe(3);

    const expectedHeadings = ["TRUTH", "RELEVANCE", "SENTIMENT"];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i] as HTMLElement;
      const cells = row.querySelectorAll('[data-slot="table-cell"]');
      expect(cells.length).toBeGreaterThanOrEqual(2);
      const headingCell = cells[0] as HTMLElement;
      expect(headingCell.getAttribute("aria-hidden")).toBeNull();
      expect(headingCell.textContent?.trim()).toBe(expectedHeadings[i]);
      expect(headingCell.className).toContain("uppercase");
      expect(headingCell.className).toContain("tracking-[0.06em]");
      expect(headingCell.className).toContain("text-muted-foreground");
      expect(headingCell.className).toContain("text-xs");
      expect(headingCell.className).not.toMatch(/text-\[12px\]/);
    }
  });

  it("renders the value chip at text-lg with rounded-md (de-pilled)", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const className = screen.getByTestId("weather-truth-value").className;
    expect(className).toContain("text-lg");
    expect(className).toContain("rounded-md");
    expect(className).not.toContain("rounded-full");
  });

  it("value chip recipe drops tinted background (no bg- token)", () => {
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
});
