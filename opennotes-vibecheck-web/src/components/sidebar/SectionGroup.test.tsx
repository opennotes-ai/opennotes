import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { readFileSync } from "node:fs";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";
import SectionGroup, { type SlugToSlots, type SectionGroupProps } from "./SectionGroup";
import Sidebar from "./Sidebar";
import type { SectionSlug, SidebarPayload } from "~/lib/api-client.server";
import { makeEmptyScd } from "~/lib/sidebar-defaults";

const { retrySectionActionMock } = vi.hoisted(() => ({
  retrySectionActionMock: vi.fn(),
}));

vi.mock("~/routes/analyze.data", () => {
  const stub = Object.assign(vi.fn(), {
    base: "/__mock_retry_action",
    url: "/__mock_retry_action",
    with: () => stub,
  });
  return { retrySectionAction: stub };
});

vi.mock("@solidjs/router", async () => {
  const actual = await vi.importActual<typeof import("@solidjs/router")>(
    "@solidjs/router",
  );
  return {
    ...actual,
    useAction: () => retrySectionActionMock,
  };
});

const TONE_SLUGS: SectionSlug[] = [
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
];

const FACTS_SLUGS: SectionSlug[] = [
  "facts_claims__dedup",
  "facts_claims__evidence",
  "facts_claims__premises",
  "facts_claims__known_misinfo",
];

function makeTonePayload(): SidebarPayload {
  return {
    source_url: "https://example.com/post",
    page_title: "Example",
    page_kind: "other",
    utterance_stream_type: "unknown",
    scraped_at: "2026-04-22T00:00:00Z",
    cached: false,
    cached_at: null,
    safety: { harmful_content_matches: [] },
    tone_dynamics: {
      scd: makeEmptyScd(),
      flashpoint_matches: [],
    },
    facts_claims: {
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
      },
      known_misinformation: [],
    },
    opinions_sentiments: {
      opinions_report: {
        sentiment_stats: {
          per_utterance: [],
          positive_pct: 0,
          negative_pct: 0,
          neutral_pct: 100,
          mean_valence: 0,
        },
        subjective_claims: [],
      },
      trends_oppositions: {
        trends: [],
        oppositions: [],
        input_cluster_count: 2,
        skipped_for_cap: 0,
      },
    },
  };
}

function imageModerationSections(matches: unknown[]): SlugToSlots {
  return {
    safety__image_moderation: {
      state: "done",
      attempt_id: "s-image",
      data: { matches },
    },
  };
}

function clearImageMatch(id: string) {
  return {
    utterance_id: id,
    image_url: `https://cdn.example.test/${id}.jpg`,
    adult: 0,
    violence: 0,
    racy: 0,
    medical: 0,
    spoof: 0,
    flagged: false,
    max_likelihood: 0,
  };
}

function flaggedImageMatch(id: string) {
  return {
    ...clearImageMatch(id),
    flagged: true,
    adult: 0.82,
    max_likelihood: 0.82,
  };
}

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  retrySectionActionMock.mockReset();
});

function expectAttribute(
  node: Element,
  name: string,
  value: string | null,
): void {
  expect(node.getAttribute(name)).toBe(value);
}

function expectHasAttribute(
  node: Element,
  name: string,
  expected: boolean,
): void {
  expect(node.hasAttribute(name)).toBe(expected);
}

describe("SectionGroup", () => {
  it("renders a 0/N counter with dim labels when all slots are pending", () => {
    const sections: SlugToSlots = {};
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{}}
      />
    ));

    const counter = screen.getByTestId("section-group-counter");
    expect(counter.textContent ?? "").toBe("0/2");
    expect(counter.getAttribute("aria-label")).toBe(
      "Tone/dynamics: 0 of 2 sections complete",
    );
    expect(counter.getAttribute("role")).toBeNull();

    for (const slug of TONE_SLUGS) {
      const label = screen.getByTestId(`slot-label-${slug}`);
      expect(label.getAttribute("data-dimmed")).toBe("true");
      expect(screen.queryByTestId(`skeleton-${slug}`)).toBeNull();
    }
  });

  it("preserves the section label as a visible <h3> heading wrapping the toggle button", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{}}
        render={{}}
      />
    ));
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading.querySelector('[data-testid="section-toggle-Tone/dynamics"]')).not.toBeNull();
    expect(heading.textContent).toContain("Tone/dynamics");
  });

  it("renders optional summary content as the first subsection before slots", () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__moderation"]}
        sections={{
          safety__moderation: {
            state: "done",
            attempt_id: "a1",
            data: { harmful_content_matches: [] },
          },
        }}
        summary={{
          label: "Summary",
          content: () => <div data-testid="summary-content">summary</div>,
          defaultOpen: true,
        }}
        render={{
          safety__moderation: () => <div data-testid="slot-content">moderation</div>,
        }}
      />
    ));

    const section = screen.getByTestId("section-group-Safety");
    const summary = within(section).getByTestId("summary-content");
    const firstSlot = within(section).getByTestId("slot-safety__moderation");
    expect(
      (summary.compareDocumentPosition(firstSlot) & Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
  });

  it("collapses and re-expands the section summary while keeping the body in the DOM", async () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__moderation"]}
        sections={{
          safety__moderation: {
            state: "done",
            attempt_id: "a1",
            data: { harmful_content_matches: [] },
          },
        }}
        summary={{
          label: "Summary",
          content: () => <div data-testid="summary-content">summary</div>,
          defaultOpen: true,
        }}
        render={{
          safety__moderation: () => <div data-testid="slot-content">moderation</div>,
        }}
      />
    ));

    const collapseLabel = "Collapse Summary in Safety";
    const expandLabel = "Expand Summary in Safety";

    const summaryToggle = screen.getByRole("button", { name: collapseLabel });
    expect(summaryToggle).toBeTruthy();
    const summaryBody = summaryToggle.closest("[data-testid='section-summary-Safety']")!.querySelector("[id]") as HTMLElement;
    expect(summaryBody).not.toBeNull();
    expectHasAttribute(summaryBody, "hidden", false);
    expect(summaryToggle.getAttribute("aria-expanded")).toBe("true");

    await fireEvent.click(summaryToggle);
    expectHasAttribute(summaryBody, "hidden", true);
    expect(summaryBody.getAttribute("aria-hidden")).toBe("true");
    expect(
      screen.getByRole("button", { name: expandLabel }).getAttribute(
        "aria-expanded",
      ),
    ).toBe("false");

    await fireEvent.click(screen.getByRole("button", { name: expandLabel }));
    expectHasAttribute(summaryBody, "hidden", false);
    expect(summaryBody.getAttribute("aria-hidden")).toBe("false");
  });

  it("does not render a summary section when summary props are omitted", () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__moderation"]}
        sections={{
          safety__moderation: {
            state: "done",
            attempt_id: "a1",
            data: { harmful_content_matches: [] },
          },
        }}
        render={{
          safety__moderation: () => <div data-testid="slot-content">moderation</div>,
        }}
      />
    ));

    expect(screen.queryByTestId("section-summary-Safety")).toBeNull();
  });

  it("preserves summary collapse state when summary prop transitions from absent to present", async () => {
    const [summaryProp, setSummaryProp] = createSignal<SectionGroupProps["summary"]>(undefined);
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__moderation"]}
        sections={{
          safety__moderation: {
            state: "done",
            attempt_id: "a1",
            data: { harmful_content_matches: [] },
          },
        }}
        summary={summaryProp()}
        render={{}}
      />
    ));

    setSummaryProp({
      label: "Summary",
      content: () => <div data-testid="summary-content">summary</div>,
      defaultOpen: true,
    });

    const summaryToggle = screen.getByTestId("section-summary-toggle-Safety");
    expect(summaryToggle.getAttribute("aria-expanded")).toBe("true");

    await fireEvent.click(summaryToggle);
    expect(summaryToggle.getAttribute("aria-expanded")).toBe("false");

    setSummaryProp({
      label: "Summary",
      content: () => <div data-testid="summary-content-v2">updated summary</div>,
      defaultOpen: true,
    });

    expect(summaryToggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("defaults each section group to expanded", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{ reasoning: "heated exchange" }] },
          },
        }}
        render={{}}
      />
    ));

    const toggle = screen.getByRole("button", {
      name: "Collapse Tone/dynamics section",
    });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const body = screen.getByTestId("section-group-body-tone-dynamics");
    expectHasAttribute(body, "hidden", false);
  });

  it("keeps section summary inside the section body so section collapse hides it too", async () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__moderation"]}
        sections={{
          safety__moderation: {
            state: "done",
            attempt_id: "a1",
            data: { harmful_content_matches: [] },
          },
        }}
        summary={{
          label: "Summary",
          content: () => <div data-testid="summary-content">summary</div>,
          defaultOpen: true,
        }}
        render={{
          safety__moderation: () => <div data-testid="slot-content">moderation</div>,
        }}
      />
    ));

    const sectionToggle = screen.getByRole("button", {
      name: "Collapse Safety section",
    });
    const sectionBody = screen.getByTestId("section-group-body-safety");

    expectHasAttribute(sectionBody, "hidden", false);
    await fireEvent.click(sectionToggle);
    expectHasAttribute(sectionBody, "hidden", true);
    expect(sectionBody.getAttribute("aria-hidden")).toBe("true");
  });

  it("assigns aria-controls to the section toggle and keeps the body id on the body", () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__moderation"]}
        sections={{
          safety__moderation: {
            state: "done",
            attempt_id: "a1",
            data: { harmful_content_matches: [] },
          },
        }}
        render={{
          safety__moderation: () => <div data-testid="slot-content">moderation</div>,
        }}
      />
    ));

    const sectionBody = screen.getByTestId("section-group-body-safety");
    const sectionToggle = screen.getByTestId("section-toggle-Safety");

    expect(sectionToggle.getAttribute("aria-controls")).toBe(
      sectionBody.getAttribute("id"),
    );
    expectHasAttribute(sectionBody, "aria-controls", false);
  });

  it("collapses and re-expands a section group while preserving the heading", async () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{ reasoning: "heated exchange" }] },
          },
        }}
        render={{}}
      />
    ));

    const toggle = screen.getByRole("button", {
      name: "Collapse Tone/dynamics section",
    });
    const body = screen.getByTestId("section-group-body-tone-dynamics");

    expectHasAttribute(body, "hidden", false);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("heading", { level: 3 })).toBeTruthy();

    await fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-label")).toBe("Expand Tone/dynamics section");
    expectHasAttribute(body, "hidden", true);

    await fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(toggle.getAttribute("aria-label")).toBe("Collapse Tone/dynamics section");
    expectHasAttribute(body, "hidden", false);
  });

  it("keeps the section counter visible when the section body is collapsed", async () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{ reasoning: "heated exchange" }] },
          },
          tone_dynamics__scd: {
            state: "done",
            attempt_id: "a2",
            data: { scd: makeEmptyScd() },
          },
        }}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
          tone_dynamics__scd: () => <div data-testid="scd-rendered" />,
        }}
      />
    ));

    const toggle = screen.getByRole("button", {
      name: "Collapse Tone/dynamics section",
    });
    const counter = screen.getByTestId("section-group-counter");

    expect(counter.textContent).toContain("2/2");
    await fireEvent.click(toggle);
    expect(counter).toBeDefined();
    expect(counter.textContent).toBe("2/2");
    expectHasAttribute(
      screen.getByTestId("section-group-body-tone-dynamics"),
      "hidden",
      true,
    );
  });

  it("maintains independent open state across section groups", async () => {
    render(() => (
      <>
        <SectionGroup
          label="Safety"
          slugs={["safety__image_moderation"]}
          sections={{
            safety__image_moderation: {
              state: "done",
              attempt_id: "s-image",
              data: { matches: [clearImageMatch("one")] },
            },
          }}
          render={{
            safety__image_moderation: () => <div data-testid="safety-rendered" />,
          }}
        />
        <SectionGroup
          label="Facts/claims"
          slugs={FACTS_SLUGS}
          sections={{
            facts_claims__dedup: {
              state: "done",
              attempt_id: "f-dedup",
              data: {
                claims_report: {
                  deduped_claims: [],
                  total_claims: 0,
                  total_unique: 0,
                },
              },
            },
          }}
          render={{}}
        />
      </>
    ));

    const safetyToggle = screen.getByRole("button", {
      name: "Collapse Safety section",
    });
    const factsToggle = screen.getByRole("button", {
      name: "Collapse Facts/claims section",
    });
    const safetyBody = screen.getByTestId("section-group-body-safety");
    const factsBody = screen.getByTestId("section-group-body-facts-claims");

    expectHasAttribute(safetyBody, "hidden", false);
    expectHasAttribute(factsBody, "hidden", false);

    await fireEvent.click(safetyToggle);
    expectHasAttribute(safetyBody, "hidden", true);
    expectAttribute(safetyBody, "aria-hidden", "true");
    expectHasAttribute(factsBody, "hidden", false);
    expectAttribute(factsBody, "aria-hidden", "false");

    await fireEvent.click(factsToggle);
    expectHasAttribute(factsBody, "hidden", true);
    expectAttribute(factsBody, "aria-hidden", "true");
    expectHasAttribute(safetyBody, "hidden", true);

    await fireEvent.click(safetyToggle);
    expectHasAttribute(safetyBody, "hidden", false);
    expectAttribute(safetyBody, "aria-hidden", "false");
    expectHasAttribute(factsBody, "hidden", true);
  });

  it("does not render the counter when the group has no slots", () => {
    render(() => (
      <SectionGroup label="Empty" slugs={[]} sections={{}} render={{}} />
    ));

    expect(screen.queryByTestId("section-group-counter")).toBeNull();
  });

  it("keeps only the dedicated hidden announcement node live", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{}}
        render={{}}
      />
    ));

    const counter = screen.getByTestId("section-group-counter");
    expect(counter.getAttribute("role")).toBeNull();
    expect(counter.getAttribute("aria-live")).toBeNull();

    const announce = screen.getByTestId("section-group-announce-Tone/dynamics");
    expect(announce.getAttribute("role")).toBe("status");
    expect(announce.getAttribute("aria-live")).toBe("polite");
  });

  it("does not announce done slots that are already complete on initial mount", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "cached-a1",
            data: { flashpoint_matches: [] },
          },
        }}
        render={{}}
      />
    ));

    expect(
      screen.getByTestId("section-group-announce-Tone/dynamics").textContent,
    ).toBe("");
  });

  it("announces a slot that completes after initial mount", () => {
    const [sections, setSections] = createSignal<SlugToSlots>({
      tone_dynamics__flashpoint: { state: "pending", attempt_id: "" },
    });
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections()}
        render={{}}
      />
    ));

    expect(
      screen.getByTestId("section-group-announce-Tone/dynamics").textContent,
    ).toBe("");

    setSections({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
    });

    expect(
      screen.getByTestId("section-group-announce-Tone/dynamics").textContent,
    ).toBe("Flashpoint complete");
  });

  it("clears announcement history when jobId changes", () => {
    const [jobId, setJobId] = createSignal("job-a");
    const [sections, setSections] = createSignal<SlugToSlots>({
      tone_dynamics__flashpoint: { state: "pending", attempt_id: "" },
    });
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections()}
        render={{}}
        jobId={jobId()}
      />
    ));

    setSections({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-1",
        data: { flashpoint_matches: [] },
      },
    });
    expect(
      screen.getByTestId("section-group-announce-Tone/dynamics").textContent,
    ).toBe("Flashpoint complete");

    setJobId("job-b");
    setSections({
      tone_dynamics__flashpoint: { state: "pending", attempt_id: "" },
    });
    expect(
      screen.getByTestId("section-group-announce-Tone/dynamics").textContent,
    ).toBe("");

    setSections({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-1",
        data: { flashpoint_matches: [] },
      },
    });
    expect(
      screen.getByTestId("section-group-announce-Tone/dynamics").textContent,
    ).toBe("Flashpoint complete");
  });

  it("renders a slug's content-shape skeleton when that slot is running", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: { state: "running", attempt_id: "a1" },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{}}
      />
    ));

    expect(
      screen.getByTestId("skeleton-tone_dynamics__flashpoint"),
    ).toBeDefined();
    expect(screen.queryByTestId("skeleton-tone_dynamics__scd")).toBeNull();

    const flashLabel = screen.getByTestId("slot-label-tone_dynamics__flashpoint");
    const scdLabel = screen.getByTestId("slot-label-tone_dynamics__scd");
    expect(flashLabel.getAttribute("data-dimmed")).toBe("false");
    expect(scdLabel.getAttribute("data-dimmed")).toBe("true");
  });

  it("shows 1/2 counter with done + failed, and renders Retry for the failed slot", () => {
    const onRetry = vi.fn();
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: {
        state: "failed",
        attempt_id: "a2",
        error: "boom",
      },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
        onRetry={onRetry}
      />
    ));

    expect(screen.getByTestId("section-group-counter").textContent).toContain(
      "1/2",
    );
    expect(screen.getByTestId("fp-rendered")).toBeDefined();

    const retry = screen.getByTestId("retry-tone_dynamics__scd");
    expect(retry).toBeDefined();
    expect(
      screen.getByText(/Couldn't run this analysis/i),
    ).toBeDefined();
  });

  it("invokes onRetry with the slug when Retry is clicked", async () => {
    const onRetry = vi.fn();
    const sections: SlugToSlots = {
      facts_claims__dedup: {
        state: "failed",
        attempt_id: "a1",
        error: "boom",
      },
      facts_claims__known_misinfo: { state: "pending", attempt_id: "" },
    };
    render(() => (
      <SectionGroup
        label="Facts/claims"
        slugs={FACTS_SLUGS}
        sections={sections}
        render={{}}
        onRetry={onRetry}
      />
    ));

    await fireEvent.click(screen.getByTestId("retry-facts_claims__dedup"));
    expect(onRetry).toHaveBeenCalledWith("facts_claims__dedup");
  });

  it("shows full counter and no skeletons when every slot is done", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: {
        state: "done",
        attempt_id: "a2",
        data: makeEmptyScd({
          summary: "done",
          insufficient_conversation: false,
        }),
      },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
          tone_dynamics__scd: () => <div data-testid="scd-rendered" />,
        }}
      />
    ));

    expect(screen.getByTestId("section-group-counter").textContent).toContain(
      "2/2",
    );
    expect(
      screen.queryByTestId("skeleton-tone_dynamics__flashpoint"),
    ).toBeNull();
    expect(screen.queryByTestId("skeleton-tone_dynamics__scd")).toBeNull();
    expect(screen.getByTestId("fp-rendered")).toBeDefined();
    expect(screen.getByTestId("scd-rendered")).toBeDefined();
  });

  it("does not remount a done slot's rendered child when polling re-fires sections with the same attempt_id", () => {
    // Regression: the analyze page polls ~1.5s and hands a freshly-parsed
    // `sections` object to Sidebar → SectionGroup on every tick. Without
    // memoization, the done-slot render function re-ran each tick, producing
    // a new child DOM subtree and visibly flickering <img>/<iframe> children
    // (mirrors the PageFrame iframe fix in PR #409).
    const renderCount = vi.fn();
    const [sections, setSections] = createSignal<SlugToSlots>({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-stable",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });

    const { container } = render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections()}
        render={{
          tone_dynamics__flashpoint: (data) => {
            renderCount();
            return (
              <div data-testid="fp-body">
                <span data-kind="marker">{String((data as { mark?: string }).mark ?? "")}</span>
              </div>
            );
          },
        }}
      />
    ));

    const firstBody = container.querySelector('[data-testid="fp-body"]');
    expect(firstBody).not.toBeNull();
    expect(renderCount).toHaveBeenCalledTimes(1);

    // Simulate a polling tick: brand-new object references, identical content,
    // same attempt_id. The memo keyed on attempt_id should reuse the rendered
    // subtree and the DOM node reference must survive.
    setSections({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-stable",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });

    const secondBody = container.querySelector('[data-testid="fp-body"]');
    expect(secondBody).toBe(firstBody);
    expect(renderCount).toHaveBeenCalledTimes(1);

    // Retry case: attempt_id changes -> memo should rebuild so new data shows.
    setSections({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-retry",
        data: { flashpoint_matches: [], mark: "after-retry" },
      },
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });

    const thirdBody = container.querySelector('[data-testid="fp-body"]');
    expect(thirdBody).not.toBe(firstBody);
    expect(renderCount).toHaveBeenCalledTimes(2);
    expect(
      container.querySelector('[data-kind="marker"]')?.textContent,
    ).toBe("after-retry");
  });

  it("wraps done content in a reveal wrapper carrying the slot attempt id", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-xyz",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    };
    const { container } = render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{
          tone_dynamics__flashpoint: () => (
            <div data-testid="fp-rendered">flash</div>
          ),
        }}
      />
    ));

    const reveal = container.querySelector<HTMLDivElement>(".section-reveal");
    expect(reveal).not.toBeNull();
    expect(reveal?.getAttribute("data-slot-attempt-id")).toBe("attempt-xyz");
  });

  it("renders the production RetryButton (not the legacy fallback) when jobId is set", async () => {
    retrySectionActionMock.mockResolvedValue({ ok: true });
    const onRetry = vi.fn();
    const sections: SlugToSlots = {
      facts_claims__dedup: {
        state: "failed",
        attempt_id: "a1",
        error: "boom",
      },
      facts_claims__known_misinfo: { state: "pending", attempt_id: "" },
    };
    render(() => (
      <SectionGroup
        label="Facts/claims"
        slugs={FACTS_SLUGS}
        sections={sections}
        render={{}}
        jobId="job-real"
        onRetry={onRetry}
      />
    ));

    const btn = screen.getByTestId(
      "retry-facts_claims__dedup",
    ) as HTMLButtonElement;
    expect(btn.getAttribute("data-in-flight")).toBe("false");
    expect(btn.getAttribute("aria-label")).toMatch(/^Retry /);

    fireEvent.click(btn);

    await waitFor(() => {
      expect(retrySectionActionMock).toHaveBeenCalledTimes(1);
    });
    const fd = retrySectionActionMock.mock.calls[0][0] as FormData;
    expect(fd.get("job_id")).toBe("job-real");
    expect(fd.get("slug")).toBe("facts_claims__dedup");
    await waitFor(() => {
      expect(onRetry).toHaveBeenCalledWith("facts_claims__dedup");
    });
  });

  it("renders running slot rows without extra wrapper content", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: { state: "running", attempt_id: "a1" },
      tone_dynamics__scd: { state: "running", attempt_id: "a2" },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{}}
      />
    ));

    expect(
      screen
        .getByTestId("slot-tone_dynamics__flashpoint")
        .getAttribute("data-slot-state"),
    ).toBe("running");
    expect(screen.getByTestId("skeleton-tone_dynamics__flashpoint")).toBeDefined();
  });

  it("renders a chevron icon (not a +/- glyph) on the slot toggle and rotates it when expanded", async () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{ tone_dynamics__flashpoint: { state: "pending", attempt_id: "" } }}
        render={{}}
      />
    ));

    const toggle = screen.getByTestId(
      "slot-toggle-tone_dynamics__flashpoint",
    );

    expect(toggle.textContent ?? "").not.toContain("+");
    expect(toggle.textContent ?? "").not.toContain("-");

    const chevron = toggle.querySelector('[data-testid="slot-chevron"]');
    expect(chevron).not.toBeNull();
    expect(chevron?.tagName.toLowerCase()).toBe("svg");
    expect(chevron?.getAttribute("data-icon")).toBe("chevron-down");
    expect(chevron?.getAttribute("data-state")).toBe("collapsed");

    await fireEvent.click(toggle);
    expect(chevron?.getAttribute("data-state")).toBe("expanded");
  });

  it("renders slot toggles as accessible controls", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{ tone_dynamics__flashpoint: { state: "pending", attempt_id: "" } }}
        render={{}}
      />
    ));

    const toggle = screen.getByTestId(
      "slot-toggle-tone_dynamics__flashpoint",
    );
    expect(toggle.tagName.toLowerCase()).toBe("button");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("renders accessible help affordances for the group and each slot", async () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__image_moderation"]}
        sections={{ safety__image_moderation: { state: "pending", attempt_id: "" } }}
        render={{}}
      />
    ));

    const sectionHelp = screen.getByTestId("section-help-Safety");
    expect(sectionHelp.getAttribute("aria-label")).toBe(
      "What does Safety mean?",
    );
    await fireEvent.click(sectionHelp);
    expect(
      (await screen.findByTestId("section-help-content-Safety")).textContent,
    ).toContain("What we look for");

    const slotHelp = screen.getByTestId(
      "slot-help-safety__image_moderation",
    );
    expect(slotHelp.getAttribute("aria-label")).toBe(
      "What does Images mean?",
    );
    await fireEvent.click(slotHelp);
    const slotHelpContent = await screen.findByTestId(
      "slot-help-content-safety__image_moderation",
    );
    expect(slotHelpContent.textContent).toContain("What these results mean");
  });

  it("renders a result-count badge for done slots", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{}, {}, {}] },
          },
          tone_dynamics__scd: {
            state: "done",
            attempt_id: "a2",
            data: { scd: makeEmptyScd() },
          },
        }}
        render={{}}
        counts={{
          tone_dynamics__flashpoint: (data) => ({
            total: ((data as { flashpoint_matches?: unknown[] }).flashpoint_matches ??
              []).length,
          }),
          tone_dynamics__scd: () => ({ total: 0 }),
        }}
      />
    ));

    const flashBadge = screen.getByTestId(
      "slot-count-tone_dynamics__flashpoint",
    );
    expect(flashBadge.textContent).toBe("3 results");

    const scdBadge = screen.getByTestId("slot-count-tone_dynamics__scd");
    expect(scdBadge.textContent).toBe("no results");
  });

  it("shows explicit flagged-of-total badge counts only when requested", () => {
    render(() => (
      <SectionGroup
        label="Safety"
        slugs={["safety__web_risk", "safety__image_moderation"]}
        sections={{
          safety__web_risk: {
            state: "done",
            attempt_id: "a1",
            data: { findings: [] },
          },
          safety__image_moderation: {
            state: "done",
            attempt_id: "a2",
            data: { matches: [] },
          },
        }}
        render={{}}
        counts={{
          safety__web_risk: () => ({ flagged: 0, total: 3, kind: "flagged" }),
          safety__image_moderation: () => ({
            flagged: 2,
            total: 5,
            kind: "flagged",
          }),
        }}
      />
    ));

    expect(screen.getByTestId("slot-count-safety__web_risk").textContent).toBe(
      "0 (of 3) flagged",
    );
    expect(screen.getByTestId("slot-count-safety__image_moderation").textContent).toBe(
      "2 (of 5) flagged",
    );
  });

  it("shows no sentences scored when a sentence badge count is zero", () => {
    render(() => (
      <SectionGroup
        label="Opinions/sentiments"
        slugs={["opinions_sentiments__sentiment"]}
        sections={{
          opinions_sentiments__sentiment: {
            state: "done",
            attempt_id: "a1",
            data: { sentiment_stats: { per_utterance: [] } },
          },
        }}
        render={{}}
        counts={{
          opinions_sentiments__sentiment: () => ({
            total: 0,
            kind: "sentences",
          }),
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-count-opinions_sentiments__sentiment").textContent,
    ).toBe("no sentences scored");
  });

  it("shows based on 1 sentence when a sentence badge count is singular", () => {
    render(() => (
      <SectionGroup
        label="Opinions/sentiments"
        slugs={["opinions_sentiments__sentiment"]}
        sections={{
          opinions_sentiments__sentiment: {
            state: "done",
            attempt_id: "a1",
            data: { sentiment_stats: { per_utterance: [{}] } },
          },
        }}
        render={{}}
        counts={{
          opinions_sentiments__sentiment: () => ({
            total: 1,
            kind: "sentences",
          }),
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-count-opinions_sentiments__sentiment").textContent,
    ).toBe("based on 1 sentence");
  });

  it("shows based on N sentences when a sentence badge count is plural", () => {
    render(() => (
      <SectionGroup
        label="Opinions/sentiments"
        slugs={["opinions_sentiments__sentiment"]}
        sections={{
          opinions_sentiments__sentiment: {
            state: "done",
            attempt_id: "a1",
            data: { sentiment_stats: { per_utterance: [{}, {}, {}] } },
          },
        }}
        render={{}}
        counts={{
          opinions_sentiments__sentiment: () => ({
            total: 3,
            kind: "sentences",
          }),
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-count-opinions_sentiments__sentiment").textContent,
    ).toBe("based on 3 sentences");
  });

  it("does not render a count badge while the slot is still pending or running", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: { state: "running", attempt_id: "a1" },
          tone_dynamics__scd: { state: "pending", attempt_id: "" },
        }}
        render={{}}
        counts={{
          tone_dynamics__flashpoint: () => ({ total: 5 }),
          tone_dynamics__scd: () => ({ total: 0 }),
        }}
      />
    ));

    expect(
      screen.queryByTestId("slot-count-tone_dynamics__flashpoint"),
    ).toBeNull();
    expect(
      screen.queryByTestId("slot-count-tone_dynamics__scd"),
    ).toBeNull();
  });

  it("collapses pending slots and exposes an accessible toggle", async () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{ tone_dynamics__flashpoint: { state: "pending", attempt_id: "" } }}
        render={{}}
      />
    ));

    const toggle = screen.getByTestId(
      "slot-toggle-tone_dynamics__flashpoint",
    );
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });

  it("slot toggle on Space key toggles state exactly once (no double-toggle)", async () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{ reasoning: "heated" }] },
          },
        }}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
      />
    ));

    const toggle = screen.getByTestId("slot-toggle-tone_dynamics__flashpoint");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    await fireEvent.keyDown(toggle, { key: " " });
    await fireEvent.keyUp(toggle, { key: " " });
    await fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("section toggle on Space key toggles state exactly once (no double-toggle)", async () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{}}
        render={{}}
      />
    ));

    const toggle = screen.getByTestId("section-toggle-Tone/dynamics");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    await fireEvent.keyDown(toggle, { key: " " });
    await fireEvent.keyUp(toggle, { key: " " });
    await fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("collapses done slots when their data is empty", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [] },
          },
        }}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
        emptinessChecks={{
          tone_dynamics__flashpoint: (data) =>
            ((data as { flashpoint_matches?: unknown[] }).flashpoint_matches ?? [])
              .length === 0,
        }}
      />
    ));

    expect(
      screen
        .getByTestId("slot-toggle-tone_dynamics__flashpoint")
        .getAttribute("aria-expanded"),
    ).toBe("false");
    expect(screen.queryByTestId("fp-rendered")).toBeNull();
  });

  it("opens done slots when their data is non-empty", () => {
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{ reasoning: "heated exchange" }] },
          },
        }}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
        emptinessChecks={{
          tone_dynamics__flashpoint: (data) =>
            ((data as { flashpoint_matches?: unknown[] }).flashpoint_matches ?? [])
              .length === 0,
        }}
      />
    ));

    expect(
      screen
        .getByTestId("slot-toggle-tone_dynamics__flashpoint")
        .getAttribute("aria-expanded"),
    ).toBe("true");
    expect(screen.getByTestId("fp-rendered")).toBeDefined();
  });

  it("keeps a user toggle sticky across polling data changes", async () => {
    const [sections, setSections] = createSignal<SlugToSlots>({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
    });
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections()}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
        emptinessChecks={{
          tone_dynamics__flashpoint: (data) =>
            ((data as { flashpoint_matches?: unknown[] }).flashpoint_matches ?? [])
              .length === 0,
        }}
      />
    ));

    const toggle = screen.getByTestId("slot-toggle-tone_dynamics__flashpoint");
    await fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    setSections({
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
    });

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("Sidebar", () => {
  it("renders all four named clusters with counters when sections is empty", () => {
    render(() => <Sidebar sections={{}} />);

    const aside = screen.getByTestId("analysis-sidebar");
    expect(aside.getAttribute("aria-live")).toBeNull();

    const counters = screen.getAllByTestId("section-group-counter");
    expect(counters).toHaveLength(4);

    expect(screen.getByTestId("section-group-Safety")).toBeDefined();
    expect(screen.getByTestId("section-group-Tone/dynamics")).toBeDefined();
    expect(screen.getByTestId("section-group-Facts/claims")).toBeDefined();
    expect(
      screen.getByTestId("section-group-Opinions/sentiments"),
    ).toBeDefined();
  });

  it("collapses top-level groups by default when requested and still lets users expand them", async () => {
    render(() => <Sidebar sections={{}} collapseTopLevelByDefault={true} />);

    const safetyToggle = screen.getByTestId("section-toggle-Safety");
    const safetyBody = screen.getByTestId("section-group-body-safety");
    expect(safetyToggle.getAttribute("aria-expanded")).toBe("false");
    expect(safetyBody.hasAttribute("hidden")).toBe(true);

    await fireEvent.click(safetyToggle);
    expect(safetyToggle.getAttribute("aria-expanded")).toBe("true");
    expect(safetyBody.hasAttribute("hidden")).toBe(false);
  });

  it("places aria-live on per-section status nodes only (not on the aside)", () => {
    render(() => <Sidebar sections={{}} />);

    const aside = screen.getByTestId("analysis-sidebar");
    expect(aside.getAttribute("aria-live")).toBeNull();

    const liveRegions = aside.querySelectorAll('[aria-live="polite"]');
    expect(liveRegions.length).toBe(4);
    for (const node of liveRegions) {
      expect(node.getAttribute("role")).toBe("status");
      expect(node.classList.contains("sr-only")).toBe(true);
    }
  });

  it("renders just the bare N/M ratio in the visible counter (no duplicated label)", () => {
    render(() => <Sidebar sections={{}} />);
    const counters = screen.getAllByTestId("section-group-counter");
    for (const c of counters) {
      const text = c.textContent ?? "";
      expect(text).toMatch(/^\d+\/\d+$/);
      const ariaLabel = c.getAttribute("aria-label") ?? "";
      expect(ariaLabel).toMatch(
        /^(Safety|Tone\/dynamics|Facts\/claims|Opinions\/sentiments): \d+\sof\s\d+\ssections complete$/,
      );
      expect(c.getAttribute("role")).toBeNull();
    }
  });

  it("synthesizes a fully-done sections map from payload when sections is absent", () => {
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      opinions_sentiments: {
        ...makeTonePayload().opinions_sentiments,
        highlights: {
          highlights: [],
          threshold: {
            total_authors: 0,
            total_utterances: 0,
            min_authors_required: 0,
            min_occurrences_required: 0,
          },
          fallback_engaged: false,
          floor_eligible_count: 0,
          total_input_count: 0,
        },
      },
    };
    render(() => <Sidebar payload={payload} payloadComplete={true} />);

    const byLabel = (label: string) =>
      within(screen.getByTestId(`section-group-${label}`)).getByTestId(
        "section-group-counter",
      );
    expect(byLabel("Safety")?.textContent).toBe("4/4");
    expect(byLabel("Tone/dynamics")?.textContent).toBe("2/2");
    expect(byLabel("Facts/claims")?.textContent).toBe("4/4");
    expect(byLabel("Opinions/sentiments")?.textContent).toBe("4/4");

    const ALL_SLUGS = [
      "safety__moderation",
      "safety__web_risk",
      "safety__image_moderation",
      "safety__video_moderation",
      "tone_dynamics__flashpoint",
      "tone_dynamics__scd",
      "facts_claims__dedup",
      "facts_claims__evidence",
      "facts_claims__premises",
      "facts_claims__known_misinfo",
      "opinions_sentiments__sentiment",
      "opinions_sentiments__trends_oppositions",
      "opinions_sentiments__highlights",
      "opinions_sentiments__subjective",
    ] as const;

    for (const slug of ALL_SLUGS) {
      expect(screen.getByTestId(`slot-${slug}`).getAttribute("data-slot-state")).toBe(
        "done",
      );
      expect(screen.queryByTestId(`skeleton-${slug}`)).toBeNull();
    }

    expect(
      screen.getByTestId("slot-count-opinions_sentiments__sentiment").textContent,
    ).toBe("no sentences scored");
  });

  it("keeps image moderation collapsed by default when no images were checked", () => {
    render(() => <Sidebar sections={imageModerationSections([])} />);

    const toggle = screen.getByTestId(
      "slot-toggle-safety__image_moderation",
    );
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("report-safety__image_moderation")).toBeNull();
    expect(
      screen.getByTestId("slot-count-safety__image_moderation").textContent,
    ).toBe("0 (of 0) flagged");
  });

  it("keeps image moderation collapsed by default when every checked image is clear", () => {
    render(() => (
      <Sidebar
        sections={imageModerationSections([
          clearImageMatch("clear-a"),
          clearImageMatch("clear-b"),
        ])}
      />
    ));

    const toggle = screen.getByTestId(
      "slot-toggle-safety__image_moderation",
    );
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("report-safety__image_moderation")).toBeNull();
    expect(
      screen.getByTestId("slot-count-safety__image_moderation").textContent,
    ).toBe("0 (of 2) flagged");
  });

  it("opens image moderation by default when at least one checked image is flagged", () => {
    render(() => (
      <Sidebar
        sections={imageModerationSections([
          flaggedImageMatch("flagged"),
          clearImageMatch("clear"),
        ])}
      />
    ));

    const toggle = screen.getByTestId(
      "slot-toggle-safety__image_moderation",
    );
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("report-safety__image_moderation")).toBeDefined();
    expect(
      screen.getByTestId("slot-count-safety__image_moderation").textContent,
    ).toBe("1 (of 2) flagged");
  });

  it("renders running sidebar slots for each supplied section", () => {
    render(() => (
      <Sidebar
        sections={{
          safety__moderation: { state: "running", attempt_id: "a1" },
          tone_dynamics__flashpoint: { state: "running", attempt_id: "a2" },
          tone_dynamics__scd: { state: "running", attempt_id: "a3" },
          facts_claims__dedup: { state: "running", attempt_id: "a4" },
          facts_claims__evidence: { state: "running", attempt_id: "a5" },
          facts_claims__premises: { state: "running", attempt_id: "a6" },
          facts_claims__known_misinfo: { state: "running", attempt_id: "a7" },
          opinions_sentiments__sentiment: { state: "running", attempt_id: "a6" },
          opinions_sentiments__subjective: { state: "running", attempt_id: "a7" },
          opinions_sentiments__trends_oppositions: {
            state: "running",
            attempt_id: "a8",
          },
          opinions_sentiments__highlights: {
            state: "running",
            attempt_id: "a9",
          },
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-safety__moderation").getAttribute("data-slot-state"),
    ).toBe("running");
    expect(
      screen.getByTestId("slot-opinions_sentiments__subjective").getAttribute("data-slot-state"),
    ).toBe("running");
    expect(
      screen.getByTestId("slot-opinions_sentiments__trends_oppositions").getAttribute("data-slot-state"),
    ).toBe("running");
    expect(
      screen.getByTestId("slot-opinions_sentiments__highlights").getAttribute("data-slot-state"),
    ).toBe("running");
  });
});

describe("Sidebar (done slots, per-slug reports)", () => {
  function doneSections(): SlugToSlots {
    return {
      safety__moderation: {
        state: "done",
        attempt_id: "s-safety",
        data: {
          harmful_content_matches: [
            {
              utterance_id: "u-safety",
              utterance_text: "This is the exact harmful sentence.",
              max_score: 0.91,
              flagged_categories: ["harassment"],
              scores: {},
              categories: { harassment: true },
              source: "openai",
            },
          ],
        },
      },
      safety__web_risk: {
        state: "done",
        attempt_id: "s-web-risk",
        data: {
          findings: [
            {
              url: "https://phishing.example.test",
              threat_types: ["SOCIAL_ENGINEERING"],
            },
          ],
          urls_checked: 3,
        },
      },
      safety__image_moderation: {
        state: "done",
        attempt_id: "s-image",
        data: {
          matches: [
            {
              utterance_id: "u-image",
              image_url: "https://cdn.example.test/image.jpg",
              adult: 0.8,
              violence: 0,
              racy: 0,
              medical: 0,
              spoof: 0,
              flagged: true,
              max_likelihood: 0.8,
            },
          ],
        },
      },
      safety__video_moderation: {
        state: "done",
        attempt_id: "s-video",
        data: {
          matches: [
            {
              utterance_id: "u-video",
              video_url: "https://video.example.test/watch.mp4",
              flagged: true,
              max_likelihood: 1,
              segment_findings: [
                {
                  start_offset_ms: 1000,
                  end_offset_ms: 1000,
                  adult: 0,
                  violence: 1,
                  racy: 0,
                  medical: 0,
                  spoof: 0,
                  flagged: true,
                  max_likelihood: 1,
                },
              ],
            },
          ],
        },
      },
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "s-flash",
        data: {
          flashpoint_matches: [
            {
              utterance_id: "u-flash",
              risk_level: "medium",
              derailment_score: 55,
              reasoning: "tone shifts sharply",
            },
          ],
        },
      },
      tone_dynamics__scd: {
        state: "done",
        attempt_id: "s-scd",
        data: {
          scd: makeEmptyScd({
            summary: "scd summary text",
            tone_labels: ["curious"],
            per_speaker_notes: { Alice: "opens with evidence" },
            insufficient_conversation: false,
          }),
        },
      },
      facts_claims__dedup: {
        state: "done",
        attempt_id: "s-dedup",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "canonical claim text",
                category: "potentially_factual",
                occurrence_count: 3,
                author_count: 2,
                utterance_ids: ["u-1"],
              },
            ],
            total_claims: 3,
            total_unique: 1,
          },
        },
      },
      facts_claims__known_misinfo: {
        state: "done",
        attempt_id: "s-known",
        data: {
          known_misinformation: [
            {
              claim_text: "known-misinfo-claim",
              textual_rating: "False",
              publisher: "factcheckers",
              review_url: "https://example.com/r",
            },
          ],
        },
      },
      opinions_sentiments__sentiment: {
        state: "done",
        attempt_id: "s-sent",
        data: {
          sentiment_stats: {
            per_utterance: [],
            positive_pct: 40,
            negative_pct: 10,
            neutral_pct: 50,
            mean_valence: 0.25,
          },
        },
      },
      opinions_sentiments__subjective: {
        state: "done",
        attempt_id: "s-subj",
        data: {
          subjective_claims: [
            { claim_text: "subjective-claim-one", stance: "positive" },
          ],
        },
      },
      opinions_sentiments__trends_oppositions: {
        state: "done",
        attempt_id: "s-trends",
        data: {
          trends_oppositions_report: {
            trends: [
              {
                label: "Policy trend",
                cluster_texts: ["cluster-a", "cluster-b"],
                summary: "Recurring policy debate.",
              },
            ],
            oppositions: [
              {
                topic: "Biden/Trump approach",
                supporting_cluster_texts: ["cluster-a"],
                opposing_cluster_texts: ["cluster-b"],
                note: "Different causal stories.",
              },
            ],
            input_cluster_count: 2,
            skipped_for_cap: 0,
          },
        },
      },
    };
  }

  it("renders each slug's own report and none of its siblings' content", () => {
    render(() => <Sidebar sections={doneSections()} />);

    const flashReport = screen.getByTestId(
      "report-tone_dynamics__flashpoint",
    );
    expect(flashReport.textContent).toContain("tone shifts sharply");
    expect(flashReport.textContent).not.toContain("scd summary text");

    const scdReport = screen.getByTestId("report-tone_dynamics__scd");
    expect(scdReport.textContent).toContain("scd summary text");
    expect(scdReport.textContent).not.toContain("tone shifts sharply");

    const safetyReport = screen.getByTestId("report-safety__moderation");
    expect(safetyReport.textContent).toContain(
      "This is the exact harmful sentence.",
    );
    expect(safetyReport.textContent).not.toContain("u-safety");

    const webRiskReport = screen.getByTestId("report-safety__web_risk");
    expect(webRiskReport.textContent).toContain(
      "https://phishing.example.test",
    );

    const imageReport = screen.getByTestId(
      "report-safety__image_moderation",
    );
    expect(imageReport.textContent).not.toContain("80%");

    const videoReport = screen.getByTestId(
      "report-safety__video_moderation",
    );
    expect(videoReport.textContent).toContain("1.0s");

    const dedupReport = screen.getByTestId("report-facts_claims__dedup");
    expect(dedupReport.textContent).toContain("canonical claim text");
    expect(dedupReport.textContent).not.toContain("known-misinfo-claim");

    const knownReport = screen.getByTestId(
      "report-facts_claims__known_misinfo",
    );
    expect(knownReport.textContent).toContain("known-misinfo-claim");
    expect(knownReport.textContent).not.toContain("canonical claim text");

    const sentimentReport = screen.getByTestId(
      "report-opinions_sentiments__sentiment",
    );
    expect(sentimentReport.textContent).toContain("40%");
    expect(sentimentReport.textContent).toContain("10%");
    expect(sentimentReport.textContent).toContain("50%");
    expect(
      within(sentimentReport)
        .getByTestId("sentiment-positive")
        .getAttribute("style"),
    ).toContain("width: 40%");
    expect(
      within(sentimentReport)
        .getByTestId("sentiment-negative")
        .getAttribute("style"),
    ).toContain("width: 10%");
    expect(
      within(sentimentReport)
        .getByTestId("sentiment-neutral")
        .getAttribute("style"),
    ).toContain("width: 50%");
    expect(sentimentReport.textContent).not.toContain(
      "subjective-claim-one",
    );
    expect(
      within(sentimentReport).queryByTestId("sentiment-mean-valence"),
    ).toBeNull();

    const subjectiveReport = screen.getByTestId(
      "report-opinions_sentiments__subjective",
    );
    expect(subjectiveReport.textContent).toContain("subjective-claim-one");
    expect(subjectiveReport.textContent).not.toContain("mean valence");

    const trendsReport = screen.getByTestId(
      "report-opinions_sentiments__trends_oppositions",
    );
    expect(trendsReport.textContent).toContain("Recurring patterns");
    expect(trendsReport.textContent).toContain("Policy trend");
    expect(trendsReport.textContent).toContain("Counter-positions");
  });

  it("suppresses stale subjective output when current highlights arrive after section data", async () => {
    const sections: SlugToSlots = {
      opinions_sentiments__subjective: {
        state: "done",
        attempt_id: "s-subj",
        data: {
          subjective_claims: [
            { claim_text: "legacy subjective dump", stance: "evaluates" },
          ],
        },
      },
      opinions_sentiments__highlights: {
        state: "done",
        attempt_id: "s-highlights",
        data: {
          highlights_report: {
            highlights: [
              {
                cluster: {
                  canonical_text: "current curated highlight",
                  category: "subjective",
                  occurrence_count: 3,
                  author_count: 2,
                  utterance_ids: ["u-highlight"],
                  representative_authors: ["author-a"],
                  facts_to_verify: 0,
                },
                crossed_scaled_threshold: true,
              },
            ],
            threshold: {
              total_authors: 2,
              total_utterances: 3,
              min_authors_required: 2,
              min_occurrences_required: 2,
            },
            fallback_engaged: false,
            floor_eligible_count: 1,
            total_input_count: 1,
          },
        },
      },
    };
    const initialPayload = makeTonePayload();
    const currentPayload: SidebarPayload = {
      ...makeTonePayload(),
      opinions_sentiments: {
        ...makeTonePayload().opinions_sentiments,
        highlights: {
          highlights: [
            {
              cluster: {
                canonical_text: "current curated highlight",
                category: "subjective",
                occurrence_count: 3,
                author_count: 2,
                utterance_ids: ["u-highlight"],
                representative_authors: ["author-a"],
                facts_to_verify: 0,
              },
              crossed_scaled_threshold: true,
            },
          ],
          threshold: {
            total_authors: 2,
            total_utterances: 3,
            min_authors_required: 2,
            min_occurrences_required: 2,
          },
          fallback_engaged: false,
          floor_eligible_count: 1,
          total_input_count: 1,
        },
      },
    };
    const [payload, setPayload] = createSignal<SidebarPayload>(initialPayload);

    render(() => (
      <Sidebar
        sections={sections}
        payload={payload()}
        payloadComplete={true}
      />
    ));

    expect(screen.queryByText("legacy subjective dump")).toBeNull();
    expect(screen.getByText("current curated highlight")).toBeDefined();

    setPayload(currentPayload);

    await waitFor(() => {
      expect(screen.queryByText("legacy subjective dump")).toBeNull();
    });
    expect(
      screen.getByTestId("report-opinions_sentiments__highlights"),
    ).toBeDefined();
    expect(screen.getByText("current curated highlight")).toBeDefined();
  });

  it("keeps legacy subjective fallback for completed payloads without highlights", () => {
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      opinions_sentiments: {
        ...makeTonePayload().opinions_sentiments,
        opinions_report: {
          ...makeTonePayload().opinions_sentiments.opinions_report,
          subjective_claims: [
            {
              claim_text: "legacy subjective dump",
              stance: "evaluates",
              utterance_id: "u-legacy",
            },
          ],
        },
      },
    };

    render(() => <Sidebar payload={payload} payloadComplete={true} />);

    expect(screen.getByText("legacy subjective dump")).toBeDefined();
    expect(
      screen.queryByTestId("report-opinions_sentiments__highlights"),
    ).toBeNull();
  });

  it("shows explicit provider names and hides non-harm confidence numbers", () => {
    const sections = doneSections();
    sections.safety__moderation = {
      state: "done",
      attempt_id: "s-safety",
      data: {
        harmful_content_matches: [
          {
            utterance_id: "u-openai",
            utterance_text: "OpenAI scored text.",
            max_score: 0.91,
            flagged_categories: ["harassment"],
            scores: {},
            categories: { harassment: true },
            source: "openai",
          },
          {
            utterance_id: "u-gcp",
            utterance_text: "GCP topic-match text.",
            max_score: 0.72,
            flagged_categories: ["toxicity"],
            scores: {},
            categories: { toxicity: true },
            source: "gcp",
          },
        ],
      },
    };

    const { container } = render(() => <Sidebar sections={sections} />);

    const labels = screen
      .getAllByTestId("safety-provider-label")
      .map((node) => node.textContent);
    expect(labels).toEqual(["OpenAI Moderation", "Google Natural Language Moderation"]);
    expect(container.textContent).toContain("91%");
    expect(container.textContent).not.toContain("72%");
    expect(screen.queryByTestId("image-moderation-max")).toBeNull();
    expect(screen.queryByTestId("video-moderation-max")).toBeNull();
  });

  it("web_risk badge total reflects urls_checked, not findings count", () => {
    render(() => (
      <Sidebar
        sections={{
          safety__web_risk: {
            state: "done",
            attempt_id: "s-web-risk",
            data: {
              findings: [
                {
                  url: "https://phishing.example.test",
                  threat_types: ["SOCIAL_ENGINEERING"],
                },
              ],
              urls_checked: 3,
            },
          },
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-count-safety__web_risk").textContent,
    ).toBe("1 (of 3) flagged");
  });

  it("web_risk badge shows 0 (of 1) flagged when page URL was checked and was clean", () => {
    render(() => (
      <Sidebar
        sections={{
          safety__web_risk: {
            state: "done",
            attempt_id: "s-web-risk",
            data: {
              findings: [],
              urls_checked: 1,
            },
          },
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-count-safety__web_risk").textContent,
    ).toBe("0 (of 1) flagged");
  });

  it("web_risk badge falls back gracefully when urls_checked is absent (legacy data)", () => {
    render(() => (
      <Sidebar
        sections={{
          safety__web_risk: {
            state: "done",
            attempt_id: "s-web-risk",
            data: {
              findings: [],
            },
          },
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-count-safety__web_risk").textContent,
    ).toBe("0 (of 0) flagged");
  });

  it("renders safety recommendation inside the Safety group and before the first Safety slot", () => {
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      safety: {
        harmful_content_matches: [],
        recommendation: {
          level: "caution",
          rationale: "Some safety analyses were unavailable.",
          top_signals: ["web risk unavailable", "video sampling inconclusive"],
          unavailable_inputs: ["web_risk", "video_moderation"],
        },
      },
    };

    render(() => <Sidebar payload={payload} payloadComplete={true} />);

    const recommendation = screen.getByTestId("safety-recommendation-report");
    const safetySection = screen.getByTestId("section-group-Safety");
    const firstSlot = within(safetySection).getByTestId("slot-safety__moderation");
    expect(recommendation.textContent).toContain("caution");
    expect(recommendation.textContent).toContain(
      "Some safety analyses were unavailable.",
    );
    expect(recommendation.textContent).toContain("web risk unavailable");
    expect(recommendation.textContent).toContain("web_risk, video_moderation");
    expect(
      (recommendation.compareDocumentPosition(firstSlot) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
    expect(safetySection.textContent).toContain("caution");
  });

  it("does not render summary when no safety recommendation is present", () => {
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      safety: {
        harmful_content_matches: [],
      },
    };

    render(() => <Sidebar payload={payload} payloadComplete={true} />);

    expect(screen.queryByTestId("safety-recommendation-report")).toBeNull();
  });

  it("hides safety recommendation when payloadComplete is false", () => {
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      safety: {
        harmful_content_matches: [],
        recommendation: {
          level: "caution",
          rationale: "Some safety analyses were unavailable.",
          top_signals: ["web risk unavailable"],
          unavailable_inputs: ["web_risk"],
        },
      },
    };

    render(() => <Sidebar payload={payload} payloadComplete={false} />);

    expect(screen.queryByTestId("safety-recommendation-report")).toBeNull();
  });

  it("hides safety recommendation when payloadComplete is omitted", () => {
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      safety: {
        harmful_content_matches: [],
        recommendation: {
          level: "caution",
          rationale: "Some safety analyses were unavailable.",
          top_signals: ["web risk unavailable"],
          unavailable_inputs: ["web_risk"],
        },
      },
    };

    render(() => <Sidebar payload={payload} />);

    expect(screen.queryByTestId("safety-recommendation-report")).toBeNull();
  });

  it("reveals safety recommendation after payloadComplete flips true", async () => {
    const [payloadComplete, setPayloadComplete] = createSignal(false);
    const payload: SidebarPayload = {
      ...makeTonePayload(),
      safety: {
        harmful_content_matches: [],
        recommendation: {
          level: "caution",
          rationale: "Some safety analyses were unavailable.",
          top_signals: ["web risk unavailable"],
          unavailable_inputs: ["web_risk"],
        },
      },
    };

    render(() => <Sidebar payload={payload} payloadComplete={payloadComplete()} />);

    expect(screen.queryByTestId("safety-recommendation-report")).toBeNull();
    setPayloadComplete(true);

    await waitFor(() => {
      expect(screen.getByTestId("safety-recommendation-report")).toBeDefined();
    });
  });

  it("renders done slot reports for completed sections", () => {
    render(() => <Sidebar sections={doneSections()} />);
    expect(screen.getByTestId("report-safety__moderation")).toBeDefined();
    expect(screen.getByTestId("report-tone_dynamics__flashpoint")).toBeDefined();
  });

  it("synthesizes identical report test ids when driven by payload only", async () => {
    const payload: SidebarPayload = {
      source_url: "https://example.com/post",
      page_title: "Example",
      page_kind: "other",
      utterance_stream_type: "unknown",
      scraped_at: "2026-04-22T00:00:00Z",
      cached: false,
      cached_at: null,
      safety: {
        harmful_content_matches: [
            {
              utterance_id: "u-p-safety",
              utterance_text: "Payload harmful sentence.",
              max_score: 0.5,
              flagged_categories: ["toxicity"],
              categories: { toxicity: true },
              scores: {},
              source: "openai",
            },
        ],
      },
      tone_dynamics: {
        scd: makeEmptyScd({
          summary: "payload summary",
          insufficient_conversation: false,
        }),
        flashpoint_matches: [],
      },
      facts_claims: {
        claims_report: {
          deduped_claims: [],
          total_claims: 0,
          total_unique: 0,
        },
        known_misinformation: [],
      },
      opinions_sentiments: {
        opinions_report: {
          sentiment_stats: {
            per_utterance: [],
            positive_pct: 10,
            negative_pct: 10,
            neutral_pct: 80,
            mean_valence: 0,
          },
          subjective_claims: [],
        },
        trends_oppositions: {
          trends: [
            {
              label: "Policy split",
              summary: "Two sides are emphasizing different causal drivers.",
              cluster_texts: ["policy-c1", "policy-c2"],
            },
          ],
          oppositions: [],
          input_cluster_count: 0,
          skipped_for_cap: 0,
        },
      },
    };
    render(() => <Sidebar payload={payload} payloadComplete={true} />);
    expect(
      screen.getByTestId("report-safety__moderation"),
    ).toBeDefined();
    await fireEvent.click(screen.getByTestId("slot-toggle-tone_dynamics__flashpoint"));
    await fireEvent.click(screen.getByTestId("slot-toggle-facts_claims__dedup"));
    await fireEvent.click(screen.getByTestId("slot-toggle-facts_claims__known_misinfo"));
    await fireEvent.click(screen.getByTestId("slot-toggle-opinions_sentiments__subjective"));
    const trendsOppositionsToggle = screen.getByTestId(
      "slot-toggle-opinions_sentiments__trends_oppositions",
    );
    if (trendsOppositionsToggle.getAttribute("aria-expanded") === "false") {
      await fireEvent.click(trendsOppositionsToggle);
    }
    expect(
      screen.getByTestId("report-tone_dynamics__flashpoint"),
    ).toBeDefined();
    expect(screen.getByTestId("report-tone_dynamics__scd")).toBeDefined();
    expect(
      screen.getByTestId("report-facts_claims__dedup"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-facts_claims__known_misinfo"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__sentiment"),
    ).toBeDefined();
    expect(
      screen.getByLabelText("Sentiment: 10% positive, 10% negative, 80% neutral"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__subjective"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__trends_oppositions"),
    ).toBeDefined();

    expect(screen.getByTestId("report-safety__moderation")).toBeDefined();
  });
});

describe("app.css motion rules", () => {
  it("defines .skeleton-pulse and .section-reveal keyframes", async () => {
    const resolveCss =
      Reflect.get(import.meta, "resolve") as
        | ((url: string) => string | Promise<string>)
        | undefined;
    let appCssPath: string | undefined;
    if (resolveCss) {
      try {
        const appCssUrl = await resolveCss("../../app.css");
        if (appCssUrl.startsWith("file:")) {
          appCssPath = fileURLToPath(appCssUrl);
        }
      } catch {
        // module runner environments may not support import.meta.resolve.
      }
    }
    if (!appCssPath) {
      const appCssUrl = new URL("../../app.css", import.meta.url);
      if (appCssUrl.protocol === "file:") {
        appCssPath = fileURLToPath(appCssUrl);
      } else if (appCssUrl.pathname.startsWith("/@fs/")) {
        appCssPath = decodeURIComponent(appCssUrl.pathname.slice("/@fs/".length));
      } else if (appCssUrl.pathname.startsWith("/src/")) {
        const localTestPath = fileURLToPath(import.meta.url);
        appCssPath = resolvePath(dirname(localTestPath), "../../app.css");
      }
    }
    if (!appCssPath) {
      throw new Error(`Unable to resolve app.css path from ${import.meta.url}`);
    }

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).toMatch(/\.skeleton-pulse\b/);
    expect(appCss).toMatch(/\.section-reveal\b/);
    expect(appCss).toMatch(/@keyframes\s+skeleton-pulse-kf\b/);
    expect(appCss).toMatch(/@keyframes\s+section-reveal-kf\b/);
    expect(appCss).toMatch(/\.skeleton-pulse-delay-1\b/);
    expect(appCss).toMatch(/\.skeleton-pulse-delay-2\b/);
    expect(appCss).toMatch(/\.skeleton-pulse-delay-3\b/);
    expect(appCss).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.skeleton-pulse-delay-\d[\s\S]*?animation:\s*none/,
    );
  });
});

describe("Sidebar (extracting-phase indicator)", () => {
  const ALL_SLUGS = [
    "safety__moderation",
    "safety__web_risk",
    "safety__image_moderation",
    "safety__video_moderation",
    "tone_dynamics__flashpoint",
    "tone_dynamics__scd",
    "facts_claims__dedup",
    "facts_claims__evidence",
    "facts_claims__premises",
    "facts_claims__known_misinfo",
    "opinions_sentiments__sentiment",
    "opinions_sentiments__trends_oppositions",
    "opinions_sentiments__highlights",
    "opinions_sentiments__subjective",
  ] as const;

  it("renders the extracting indicator and per-slug skeletons when jobStatus is extracting and sections is empty", () => {
    render(() => <Sidebar sections={{}} jobStatus="extracting" />);

    const indicator = screen.getByTestId("extracting-indicator");
    expect(indicator).toBeDefined();
    expect(indicator.getAttribute("role")).toBe("status");
    expect(indicator.textContent ?? "").toMatch(/extracting/i);

    // Every slot should be in `running` state so its content-shape skeleton renders.
    for (const slug of ALL_SLUGS) {
      const slot = screen.getByTestId(`slot-${slug}`);
      expect(slot.getAttribute("data-slot-state")).toBe("running");
    }

    // At least one skeleton per group is present (proves the per-slug
    // skeleton path is what's rendering, not a generic placeholder).
    // Note: the four safety slugs all reuse SafetyModerationSkeleton, so
    // its testid appears multiple times — getAllByTestId asserts presence
    // without imposing uniqueness.
    expect(
      screen.getAllByTestId("skeleton-safety__moderation").length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId("skeleton-tone_dynamics__flashpoint")).toBeDefined();
    expect(
      screen.getAllByTestId("skeleton-facts_claims__dedup").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByTestId("skeleton-opinions_sentiments__sentiment").length,
    ).toBeGreaterThan(0);
  });

  it("does not render the extracting indicator when jobStatus is done (cached-hit path)", () => {
    const payload = makeTonePayload();
    render(() => <Sidebar payload={payload} jobStatus="done" />);

    expect(screen.queryByTestId("extracting-indicator")).toBeNull();
    // And no per-slot skeletons should render — the payload-synthesized
    // sections are all `done`. Use queryAllByTestId because some slugs
    // share a skeleton component (and thus a testid).
    for (const slug of ALL_SLUGS) {
      expect(screen.queryAllByTestId(`skeleton-${slug}`)).toHaveLength(0);
    }
  });

  it("does not render the extracting indicator when jobStatus is omitted", () => {
    render(() => <Sidebar sections={{}} />);
    expect(screen.queryByTestId("extracting-indicator")).toBeNull();
  });

  it("does not render the extracting indicator when jobStatus is failed", () => {
    render(() => <Sidebar sections={{}} jobStatus="failed" />);
    expect(screen.queryByTestId("extracting-indicator")).toBeNull();
  });

  it("preserves real slot states once analyzing starts (server-seeded slots win)", () => {
    // The server may already have promoted one slot to running and another
    // to done in the same poll where status flips to analyzing. Make sure
    // we don't clobber those with synthesized running slots.
    render(() => (
      <Sidebar
        jobStatus="analyzing"
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [] },
          },
          tone_dynamics__scd: { state: "running", attempt_id: "a2" },
        }}
      />
    ));

    // Indicator now renders during analyzing to show backend activity labels.
    expect(screen.getByTestId("extracting-indicator")).toBeDefined();
    expect(
      screen
        .getByTestId("slot-tone_dynamics__flashpoint")
        .getAttribute("data-slot-state"),
    ).toBe("done");
    expect(
      screen
        .getByTestId("slot-tone_dynamics__scd")
        .getAttribute("data-slot-state"),
    ).toBe("running");
    // Slots the server hasn't seeded yet render as running during analyzing
    // so the sidebar does not go blank below the activity indicator.
    expect(
      screen.getByTestId("slot-safety__moderation").getAttribute("data-slot-state"),
    ).toBe("running");
  });
});

describe("Sidebar (partial payload)", () => {
  it("does not synthesize all-done slots from payload when payloadComplete is false", () => {
    const payload = makeTonePayload();
    render(() => <Sidebar payload={payload} payloadComplete={false} />);

    expect(
      screen.getByTestId("slot-safety__moderation").getAttribute("data-slot-state"),
    ).toBe("pending");
    expect(
      screen.getByTestId("slot-tone_dynamics__flashpoint").getAttribute("data-slot-state"),
    ).toBe("pending");
  });

  it("synthesizes all-done slots from payload when payloadComplete is true", () => {
    const payload = makeTonePayload();
    render(() => <Sidebar payload={payload} payloadComplete={true} />);

    expect(
      screen.getByTestId("slot-safety__moderation").getAttribute("data-slot-state"),
    ).toBe("done");
    expect(screen.queryByTestId("skeleton-safety__moderation")).toBeNull();
  });

  it("renders done reports from sections while keeping skeletons for unfinished slots when payloadComplete is false", () => {
    const payload = makeTonePayload();
    render(() => (
      <Sidebar
        payload={payload}
        payloadComplete={false}
        sections={{
          tone_dynamics__flashpoint: {
            state: "done",
            attempt_id: "a1",
            data: { flashpoint_matches: [{ risk_level: "Heated", derailment_score: 55, reasoning: "heated", utterance_id: "u1", context_messages: 2, scan_type: "conversation_flashpoint" }] },
          },
          tone_dynamics__scd: { state: "running", attempt_id: "a2" },
        }}
      />
    ));

    expect(
      screen.getByTestId("slot-tone_dynamics__flashpoint").getAttribute("data-slot-state"),
    ).toBe("done");
    expect(screen.getByTestId("report-tone_dynamics__flashpoint")).toBeDefined();

    expect(
      screen.getByTestId("slot-tone_dynamics__scd").getAttribute("data-slot-state"),
    ).toBe("running");
    expect(screen.getByTestId("skeleton-tone_dynamics__scd")).toBeDefined();

    expect(
      screen.getByTestId("slot-safety__moderation").getAttribute("data-slot-state"),
    ).toBe("pending");
  });

  it("does not show headline summary or cache badge props surface only when payloadComplete is true", () => {
    const payload = makeTonePayload();
    render(() => (
      <Sidebar
        payload={payload}
        payloadComplete={false}
        jobStatus="analyzing"
      />
    ));

    // No headline summary or cached badge rendering in Sidebar itself — those
    // are routed through the Sidebar props but the partial payload should not
    // trigger final-only UI. During analyzing, missing slots still show running
    // skeletons beneath the activity indicator.
    expect(
      screen.getByTestId("slot-safety__moderation").getAttribute("data-slot-state"),
    ).toBe("running");
  });
});

describe("Sidebar (activity indicator)", () => {
  it("renders backend activity label in extracting indicator when present", () => {
    render(() => (
      <Sidebar
        sections={{}}
        jobStatus="extracting"
        activityLabel="Running section analyses"
      />
    ));

    const indicator = screen.getByTestId("extracting-indicator");
    expect(indicator.textContent).toContain("Running section analyses");
  });

  it("falls back to default copy when activityLabel is absent", () => {
    render(() => <Sidebar sections={{}} jobStatus="extracting" />);

    const indicator = screen.getByTestId("extracting-indicator");
    expect(indicator.textContent).toMatch(/extracting page content/i);
  });

  it("passes activityAt to the indicator as a data attribute", () => {
    render(() => (
      <Sidebar
        sections={{}}
        jobStatus="extracting"
        activityLabel="Running section analyses"
        activityAt="2026-04-22T00:00:00Z"
      />
    ));

    const indicator = screen.getByTestId("extracting-indicator");
    expect(indicator.getAttribute("data-activity-at")).toBe("2026-04-22T00:00:00Z");
  });
});
