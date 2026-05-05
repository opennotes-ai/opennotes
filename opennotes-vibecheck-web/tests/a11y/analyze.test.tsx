import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MetaProvider } from "@solidjs/meta";
import {
  MemoryRouter,
  Route,
  createMemoryHistory,
} from "@solidjs/router";
import { createSignal } from "solid-js";
import type { JobState, SectionSlot } from "~/lib/api-client.server";
import Sidebar from "~/components/sidebar/Sidebar";
import SectionGroup, {
  type SlugToSlots,
} from "~/components/sidebar/SectionGroup";
import RetryButton from "~/components/sidebar/RetryButton";

type PollingHandle = {
  state: () => JobState | null;
  error: () => Error | null;
  refetch: () => void;
};

const { pollingHandles } = vi.hoisted(() => ({
  pollingHandles: [] as Array<{
    setState: (v: JobState | null) => void;
    handle: PollingHandle;
  }>,
}));

vi.mock("~/lib/polling", () => ({
  createPollingResource: (
    _jobId: () => string,
    options?: { initialState?: JobState | null },
  ) => {
    const [state, setState] = createSignal<JobState | null>(
      options?.initialState ?? null,
    );
    const [error] = createSignal<Error | null>(null);
    const handle: PollingHandle = {
      state,
      error,
      refetch: () => {},
    };
    pollingHandles.push({ setState, handle });
    return handle;
  },
}));

vi.mock("~/routes/analyze.data", () => {
  const getArchiveProbeStub = Object.assign(
    vi.fn(async () => ({
      ok: true,
      has_archive: false,
      archived_preview_url: null,
      can_iframe: true,
      blocking_header: null,
      csp_frame_ancestors: null,
    })),
    {
      keyFor: (url: string) => `vibecheck-archive-probe:${url}`,
      key: "vibecheck-archive-probe",
    },
  );
  const getScreenshotStub = Object.assign(vi.fn(async () => null), {
    keyFor: (url: string) => `vibecheck-screenshot:${url}`,
    key: "vibecheck-screenshot",
  });
  const getJobStateStub = Object.assign(vi.fn(async () => null), {
    keyFor: (jobId: string) => `vibecheck-job-state:${jobId}`,
    key: "vibecheck-job-state",
  });
  const analyzeActionStub = Object.assign(vi.fn(), {
    base: "/__mock_analyze_action",
    url: "/__mock_analyze_action",
    with: () => analyzeActionStub,
  });
  const retryStub = Object.assign(vi.fn(), {
    base: "/__mock_retry_action",
    url: "/__mock_retry_action",
    with: () => retryStub,
  });
  const pollStub = vi.fn();
  return {
    getArchiveProbe: getArchiveProbeStub,
    getJobState: getJobStateStub,
    getScreenshot: getScreenshotStub,
    retrySectionAction: retryStub,
    analyzeAction: analyzeActionStub,
    pollJobState: pollStub,
  };
});

import AnalyzePage from "~/routes/analyze";

afterEach(() => {
  cleanup();
  pollingHandles.length = 0;
});

function renderRouteAt(path: string) {
  const history = createMemoryHistory();
  history.set({ value: path, scroll: false, replace: true });
  return render(() => (
    <MetaProvider>
      <MemoryRouter history={history}>
        <Route path="/analyze" component={AnalyzePage} />
      </MemoryRouter>
    </MetaProvider>
  ));
}

function runningSection(attemptId: string): SectionSlot {
  return { state: "running", attempt_id: attemptId };
}

function doneSection(attemptId: string): SectionSlot {
  return {
    state: "done",
    attempt_id: attemptId,
    data: { flashpoint_matches: [] },
  };
}

describe("AC1: cache-hit no-flash via data-cached-hint", () => {
  it("stamps data-cached-hint=1 on every slot container when Sidebar is given cachedHint", () => {
    const sections: SlugToSlots = {
      safety__moderation: runningSection("s1"),
      tone_dynamics__flashpoint: runningSection("s2"),
    };
    const { container } = render(() => (
      <Sidebar sections={sections} cachedHint />
    ));

    const marked = container.querySelectorAll('[data-cached-hint="1"]');
    expect(marked.length).toBeGreaterThan(0);
    const safetySlot = container.querySelector(
      '[data-testid="slot-safety__moderation"]',
    );
    expect(safetySlot?.getAttribute("data-cached-hint")).toBe("1");
  });

  it("does not set data-cached-hint when cachedHint is absent/false", () => {
    const sections: SlugToSlots = {
      safety__moderation: runningSection("s1"),
    };
    const { container } = render(() => (
      <Sidebar sections={sections} cachedHint={false} />
    ));
    const slot = container.querySelector(
      '[data-testid="slot-safety__moderation"]',
    );
    expect(slot?.getAttribute("data-cached-hint")).toBeNull();
  });

  it("propagates cachedHint from AnalyzePage when ?c=1 is on the URL", async () => {
    renderRouteAt("/analyze?job=job-xyz&c=1&url=https://example.com");
    const slot = await screen.findByTestId("slot-safety__moderation");
    expect(slot.getAttribute("data-cached-hint")).toBe("1");
  });

  it("does not propagate cachedHint when ?c=1 is absent", async () => {
    renderRouteAt("/analyze?job=job-xyz&url=https://example.com");
    const slot = await screen.findByTestId("slot-safety__moderation");
    expect(slot.getAttribute("data-cached-hint")).toBeNull();
  });

  it("ships CSS that hides skeleton pulses under [data-cached-hint=1]", () => {
    const appCss = readFileSync(
      resolve(process.cwd(), "src/app.css"),
      "utf8",
    );
    expect(appCss).toMatch(
      /\[data-cached-hint="1"\][^}]*\.skeleton-pulse[^}]*opacity:\s*0\s*;?/,
    );
  });
});

describe("AC2: prefers-reduced-motion disables pulse and reveal", () => {
  it("guards .skeleton-pulse animation behind prefers-reduced-motion: reduce", () => {
    const appCss = readFileSync(
      resolve(process.cwd(), "src/app.css"),
      "utf8",
    );
    const match = appCss.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?)\}\s*\}/,
    );
    expect(match).not.toBeNull();
    const block = match?.[1] ?? "";
    expect(block).toMatch(/\.skeleton-pulse[^}]*animation:\s*none/);
    expect(block).toMatch(/\.skeleton-pulse[^}]*opacity:\s*0\.55/);
    expect(block).toMatch(/\.section-reveal[^}]*animation:\s*none/);
  });
});

describe("AC3: aria-live announcement dedup", () => {
  it("announces a slot's done transition exactly once per attempt_id across re-renders", () => {
    const [sections, setSections] = createSignal<SlugToSlots>({
      tone_dynamics__flashpoint: runningSection("attempt-1"),
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={["tone_dynamics__flashpoint", "tone_dynamics__scd"]}
        sections={sections()}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
      />
    ));

    const live = screen.getByTestId("section-group-announce-Tone/dynamics");
    expect(live.getAttribute("aria-live")).toBe("polite");
    expect(live.getAttribute("role")).toBe("status");
    expect(live.textContent ?? "").toBe("");

    setSections({
      tone_dynamics__flashpoint: doneSection("attempt-1"),
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });
    expect(live.textContent).toBe("Flashpoint complete");

    setSections({
      tone_dynamics__flashpoint: doneSection("attempt-1"),
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });
    expect(live.textContent).toBe("Flashpoint complete");

    setSections({
      tone_dynamics__flashpoint: doneSection("attempt-2"),
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    });
    expect(live.textContent).toBe("Flashpoint complete");
  });

  it("announces failed transitions with the '{name} failed' phrase and dedups by attempt_id", () => {
    const [sections, setSections] = createSignal<SlugToSlots>({
      facts_claims__dedup: { state: "running", attempt_id: "dedup-1" },
      facts_claims__known_misinfo: { state: "pending", attempt_id: "" },
    });
    render(() => (
      <SectionGroup
        label="Facts/claims"
        slugs={["facts_claims__dedup", "facts_claims__known_misinfo"]}
        sections={sections()}
        render={{}}
      />
    ));

    const live = screen.getByTestId("section-group-announce-Facts/claims");
    expect(live.textContent ?? "").toBe("");

    setSections({
      facts_claims__dedup: {
        state: "failed",
        attempt_id: "dedup-1",
        error: "boom",
      },
      facts_claims__known_misinfo: { state: "pending", attempt_id: "" },
    });
    expect(live.textContent).toBe("Claims failed");

    setSections({
      facts_claims__dedup: {
        state: "failed",
        attempt_id: "dedup-1",
        error: "still boom",
      },
      facts_claims__known_misinfo: { state: "pending", attempt_id: "" },
    });
    expect(live.textContent).toBe("Claims failed");
  });
});

describe("AC4: Retry button aria-label uses section display name", () => {
  const cases: Array<[string, string]> = [
    ["safety__moderation", "Retry Safety"],
    ["tone_dynamics__flashpoint", "Retry Flashpoint"],
    ["tone_dynamics__scd", "Retry SCD"],
    ["facts_claims__dedup", "Retry Claims"],
    ["facts_claims__known_misinfo", "Retry Known misinfo"],
    ["opinions_sentiments__sentiment", "Retry Sentiment"],
    ["opinions_sentiments__subjective", "Retry Subjective claims"],
  ];

  for (const [slug, expected] of cases) {
    it(`renders aria-label="${expected}" for slug ${slug}`, () => {
      const history = createMemoryHistory();
      history.set({ value: "/analyze", scroll: false, replace: true });
      render(() => (
        <MemoryRouter history={history}>
          <Route
            path="/analyze"
            component={() => (
              <RetryButton
                jobId="job-1"
                slug={slug as never}
                slotState="failed"
              />
            )}
          />
        </MemoryRouter>
      ));
      const btn = screen.getByTestId(`retry-${slug}`);
      expect(btn.getAttribute("aria-label")).toBe(expected);
    });
  }
});
