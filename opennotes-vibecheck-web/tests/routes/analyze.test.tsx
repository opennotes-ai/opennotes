import {
  describe,
  it,
  expect,
  vi,
  afterAll,
  afterEach,
  beforeEach,
} from "vitest";
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  within,
} from "@solidjs/testing-library";
import { MetaProvider } from "@solidjs/meta";
import {
  MemoryRouter,
  Route,
  createMemoryHistory,
} from "@solidjs/router";
import { createSignal, ErrorBoundary } from "solid-js";
import type { JobState, SidebarPayload } from "~/lib/api-client.server";

type PollingHandle = {
  state: () => JobState | null;
  error: () => Error | null;
  refetch: () => void;
};

type MockFrameCompat = {
  canIframe: boolean;
  blockingHeader: string | null;
  cspFrameAncestors: string | null;
  screenshotUrl: string | null;
  archivedPreviewUrl: string | null;
};

type MockArchiveProbeResult =
  | {
      ok: true;
      has_archive: boolean;
      archived_preview_url: string | null;
      can_iframe: boolean;
      blocking_header: string | null;
      csp_frame_ancestors: string | null;
    }
  | { ok: false; kind: "transient_error" | "invalid_url" };

type GetArchiveProbeMock = (
  url: string,
  jobId?: string,
) => Promise<MockArchiveProbeResult>;

type GetScreenshotMock = (url: string) => Promise<string | null>;
type GetJobStateMock = (jobId: string) => Promise<JobState | null>;

const LONG_SERVER_HEADLINE_TEXT =
  "The terminal payload now ships a full editorial synthesis with policy context, uncertainty bounds, and a complete timeline of causality across the major actors, which would previously have been cut short when fixed-length clipping was applied to preserve card stability under strict sidebar width constraints.";
const LONG_FALLBACK_HEADLINE_TITLE =
  "The fallback title pathway must preserve long article names across normalization and punctuation while still being surfaced as a stock headline in the sidebar alongside the safety recommendation card and with full contextual fidelity";
const LONG_FALLBACK_HEADLINE_TEXT =
  `news.example.com — ${LONG_FALLBACK_HEADLINE_TITLE}`;

const { pollingHandles, refetchSpy } = vi.hoisted(() => ({
  pollingHandles: [] as Array<{
    setState: (v: JobState | null) => void;
    setError: (v: Error | null) => void;
    handle: PollingHandle;
  }>,
  refetchSpy: { current: vi.fn() },
}));

vi.mock("~/lib/polling", () => {
  return {
    createPollingResource: (
      _jobId: () => string,
      options?: { initialState?: JobState | null },
    ) => {
      const [state, setState] = createSignal<JobState | null>(
        options?.initialState ?? null,
      );
      const [error, setError] = createSignal<Error | null>(null);
      const handle: PollingHandle = {
        state,
        error,
        refetch: () => refetchSpy.current(),
      };
      pollingHandles.push({ setState, setError, handle });
      return handle;
    },
  };
});

const {
  getArchiveProbeMock,
  getScreenshotMock,
  getJobStateMock,
  revalidateMock,
  retrySectionActionMock,
} = vi.hoisted(() => ({
  getArchiveProbeMock: vi.fn<GetArchiveProbeMock>(async () => ({
    ok: true,
    has_archive: false,
    archived_preview_url: null,
    can_iframe: true,
    blocking_header: null,
    csp_frame_ancestors: null,
  })),
  getScreenshotMock: vi.fn<GetScreenshotMock>(async () => null),
  getJobStateMock: vi.fn<GetJobStateMock>(async () => null),
  revalidateMock: vi.fn(async () => undefined),
  retrySectionActionMock: vi.fn(),
}));

vi.mock("@solidjs/router", async () => {
  const actual = await vi.importActual<typeof import("@solidjs/router")>(
    "@solidjs/router",
  );
  return {
    ...actual,
    revalidate: revalidateMock,
    useAction: (action: unknown) => {
      void action;
      return retrySectionActionMock;
    },
  };
});

vi.mock("~/routes/analyze.data", () => {
  const getArchiveProbeStub = Object.assign(getArchiveProbeMock, {
    keyFor: (url: string, jobId?: string) =>
      `vibecheck-archive-probe:${url}:${jobId ?? ""}`,
    key: "vibecheck-archive-probe",
  });
  const getScreenshotStub = Object.assign(getScreenshotMock, {
    keyFor: (url: string) => `vibecheck-screenshot:${url}`,
    key: "vibecheck-screenshot",
  });
  const getJobStateStub = Object.assign(getJobStateMock, {
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

const { scrollToUtteranceMock } = vi.hoisted(() => ({
  scrollToUtteranceMock: vi.fn(() => true),
}));

vi.mock("~/lib/utterance-scroll", () => ({
  scrollToUtterance: scrollToUtteranceMock,
}));

const localStorageValues = new Map<string, string>();
const originalLocalStorageDescriptor = Object.getOwnPropertyDescriptor(
  window,
  "localStorage",
);
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: {
    getItem: (key: string) => localStorageValues.get(key) ?? null,
    setItem: (key: string, value: string) => {
      localStorageValues.set(key, value);
    },
    removeItem: (key: string) => {
      localStorageValues.delete(key);
    },
    clear: () => {
      localStorageValues.clear();
    },
  },
});

import AnalyzePage from "../../src/routes/analyze";

function resetTestEnv() {
  getArchiveProbeMock.mockReset();
  getArchiveProbeMock.mockImplementation(async () => ({
    ok: true,
    has_archive: false,
    archived_preview_url: null,
    can_iframe: true,
    blocking_header: null,
    csp_frame_ancestors: null,
  }));
  getScreenshotMock.mockReset();
  getScreenshotMock.mockImplementation(async () => null);
  getJobStateMock.mockReset();
  getJobStateMock.mockImplementation(async () => null);
  revalidateMock.mockReset();
  revalidateMock.mockImplementation(async () => undefined);
  window.localStorage.clear();
  pollingHandles.length = 0;
  refetchSpy.current.mockReset();
  retrySectionActionMock.mockReset();
  scrollToUtteranceMock.mockReset();
  scrollToUtteranceMock.mockReturnValue(true);
}

beforeEach(() => {
  resetTestEnv();
});

afterEach(() => {
  cleanup();
  resetTestEnv();
});

afterAll(() => {
  if (originalLocalStorageDescriptor) {
    Object.defineProperty(window, "localStorage", originalLocalStorageDescriptor);
  } else {
    delete (window as unknown as { localStorage?: Storage }).localStorage;
  }
});

function setPolledJobState(value: JobState | null) {
  for (const h of pollingHandles) h.setState(value);
}

function renderAt(path: string) {
  return renderAtWithHistory(path);
}

function renderAtWithHistory(path: string) {
  const history = createMemoryHistory();
  history.set({ value: path, scroll: false, replace: true });
  const rendered = render(() => (
    <MetaProvider>
      <MemoryRouter history={history}>
        <Route path="/analyze" component={AnalyzePage} />
      </MemoryRouter>
    </MetaProvider>
  ));
  return { ...rendered, history };
}

function frameCompatResult(
  overrides: Partial<MockFrameCompat> = {},
): MockArchiveProbeResult {
  const frameCompat = {
    canIframe: true,
    blockingHeader: null,
    cspFrameAncestors: null,
    screenshotUrl: null,
    archivedPreviewUrl: null,
    ...overrides,
  };
  return {
    ok: true,
    has_archive: Boolean(frameCompat.archivedPreviewUrl),
    archived_preview_url: frameCompat.archivedPreviewUrl,
    can_iframe: frameCompat.canIframe,
    blocking_header: frameCompat.blockingHeader,
    csp_frame_ancestors: frameCompat.cspFrameAncestors,
  };
}

async function flushMicrotasks() {
  for (let i = 0; i < 8; i++) {
    await Promise.resolve();
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeJobState(overrides: Partial<JobState> = {}): JobState {
  return {
    job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    url: "https://news.example.com/a",
    status: "analyzing",
    attempt_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    created_at: "2026-04-22T00:00:00Z",
    updated_at: "2026-04-22T00:00:00Z",
    cached: false,
    sidebar_payload_complete: false,
    next_poll_ms: 1500,
    utterance_count: 0,
    ...overrides,
  } as JobState;
}

function makeSidebarPayload(
  overrides: Partial<SidebarPayload> = {},
): SidebarPayload {
  return {
    source_url: "https://news.example.com/a",
    page_title: null,
    page_kind: "article",
    scraped_at: "2026-04-22T00:00:00Z",
    cached: false,
    cached_at: null,
    safety: { harmful_content_matches: [] },
    tone_dynamics: {
      scd: {
        summary: "",
        tone_labels: [],
        per_speaker_notes: {},
        insufficient_conversation: true,
      },
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
          neutral_pct: 0,
          mean_valence: 0,
        },
        subjective_claims: [],
      },
    },
    headline: null,
    ...overrides,
  } as SidebarPayload;
}

describe("AnalyzePage route", () => {
  it("renders a cached terminal seed immediately without extracting or page-frame loading indicators", async () => {
    getJobStateMock.mockResolvedValueOnce(
      makeJobState({
        status: "done",
        cached: true,
        sidebar_payload_complete: true,
        sidebar_payload: makeSidebarPayload({
          headline: {
            text: "A cached result loads immediately",
            kind: "synthesized",
            unavailable_inputs: [],
          },
        }),
      }),
    );
    const pendingProbe = deferred<MockArchiveProbeResult>();
    getArchiveProbeMock.mockReturnValueOnce(pendingProbe.promise);

    renderAt("/analyze?job=job-cached-direct");

    expect(await screen.findByTestId("analyze-layout")).not.toBeNull();
    expect(screen.getByTestId("headline-summary-text").textContent).toBe(
      "A cached result loads immediately",
    );
    expect(screen.queryByTestId("extracting-indicator")).toBeNull();
    expect(screen.queryByTestId("page-frame-loading")).toBeNull();
    expect(screen.getByTestId("page-frame-iframe")).not.toBeNull();
  });

  it("renders a cached partial seed with the partial banner and no extracting indicator", async () => {
    getJobStateMock.mockResolvedValueOnce(
      makeJobState({
        status: "partial" as JobState["status"],
        error_code: "section_failure",
        error_message: "Sections failed: safety__web_risk",
        sidebar_payload_complete: true,
        sidebar_payload: makeSidebarPayload(),
        sections: {
          safety__web_risk: {
            state: "failed",
            attempt_id: "failed-attempt",
            error: "Google Web Risk rejected URI mailto:hn@ycombinator.com",
          },
        } as unknown as JobState["sections"],
      }),
    );

    renderAt("/analyze?job=job-cached-partial");

    expect(await screen.findByTestId("analyze-layout")).not.toBeNull();
    expect(screen.getByTestId("partial-failure-banner")).not.toBeNull();
    expect(screen.queryByTestId("extracting-indicator")).toBeNull();
    expect(screen.queryByTestId("page-frame-loading")).toBeNull();
  });

  it("ignores ?pending_error when ?job is present and job is still polling (renders layout, no failure card)", async () => {
    renderAt(
      "/analyze?job=job-xyz&pending_error=unsupported_site&url=https://example.com",
    );

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });

    setPolledJobState(makeJobState({ status: "analyzing" }));

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });
    expect(screen.queryByTestId("job-failure-card")).toBeNull();
  });

  it("keeps the analyze layout mounted when the frame compatibility probe fails", async () => {
    getArchiveProbeMock.mockRejectedValueOnce(new Error("frame probe down"));

    renderAt("/analyze?job=job-probe&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(makeJobState({ status: "extracting" }));

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });
    expect(screen.queryByTestId("job-failure-card")).toBeNull();
    expect(screen.queryByTestId("page-frame-iframe")).not.toBeNull();
  });

  it("when ?job is present and job transitions to failed, renders the job-state failure (not pending_error)", async () => {
    renderAt(
      "/analyze?job=job-xyz&pending_error=unsupported_site&url=https://example.com",
    );

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "failed",
        error_code: "upstream_error",
        url: "https://news.example.com/a",
      }),
    );

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe("upstream_error");
  });

  it("passes unsafe_url Web Risk findings from JobState sidebar_payload into the failure card", async () => {
    renderAt("/analyze?job=job-unsafe&url=https://phishing.example.test");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "failed",
        error_code: "unsafe_url",
        url: "https://phishing.example.test",
        sidebar_payload: {
          web_risk: {
            findings: [
              {
                url: "https://phishing.example.test",
                threat_types: ["SOCIAL_ENGINEERING"],
              },
            ],
          },
        },
      } as unknown as Partial<JobState>),
    );

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe("unsafe_url");
    expect(screen.getByTestId("unsafe-url-finding").textContent).toContain(
      "https://phishing.example.test",
    );
    expect(screen.getByTestId("unsafe-url-threat").textContent).toBe(
      "social engineering",
    );
  });

  it("when no ?job is present, falls back to the pending_error URL param", async () => {
    renderAt(
      "/analyze?pending_error=unsupported_site&url=https://blocked.example.com&host=blocked.example.com",
    );

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe(
      "unsupported_site",
    );
  });

  it("upload_not_found in ?pending_error renders a JobFailureCard (not generic error) — TASK-1498.35", async () => {
    renderAt("/analyze?pending_error=upload_not_found&url=doc.pdf");

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe("upload_not_found");
    expect(screen.queryByTestId("analyze-empty")).toBeNull();
  });

  it("upload_key_invalid in ?pending_error renders a JobFailureCard — TASK-1498.35", async () => {
    renderAt("/analyze?pending_error=upload_key_invalid&url=doc.pdf");

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe("upload_key_invalid");
    expect(screen.queryByTestId("analyze-empty")).toBeNull();
  });

  it("invalid_pdf_type in ?pending_error renders a JobFailureCard — TASK-1498.35", async () => {
    renderAt("/analyze?pending_error=invalid_pdf_type&url=doc.pdf");

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe("invalid_pdf_type");
    expect(screen.queryByTestId("analyze-empty")).toBeNull();
  });

  it("renders CachedBadge with a timestamp when JobState.cached=true and sidebar_payload.cached_at is set (even if payload.cached is false)", async () => {
    renderAt("/analyze?job=job-cache&c=1&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "done",
        cached: true,
        sidebar_payload_complete: true,
        sidebar_payload: {
          source_url: "https://news.example.com/a",
          page_title: null,
          page_kind: "article",
          scraped_at: "2026-04-22T00:00:00Z",
          cached: false,
          cached_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
          safety: { harmful_content_matches: [] },
          tone_dynamics: {
            scd: {
              summary: "",
              tone_labels: [],
              per_speaker_notes: {},
              insufficient_conversation: true,
            },
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
                neutral_pct: 0,
                mean_valence: 0,
              },
              subjective_claims: [],
            },
          },
        },
      } as unknown as Partial<JobState>),
    );

    const badge = await screen.findByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
    expect(badge.textContent).toMatch(/ago/);
  });

  it("renders CachedBadge without a timestamp when JobState.cached=true and cached_at is null", async () => {
    renderAt("/analyze?job=job-cache-no-ts&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "done",
        cached: true,
        sidebar_payload: null,
        sidebar_payload_complete: true,
      } as unknown as Partial<JobState>),
    );

    const badge = await screen.findByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
    expect(badge.textContent?.toLowerCase()).not.toMatch(/ago/);
    expect(badge.textContent?.toLowerCase()).not.toMatch(/just now/);
  });

  it("redirects /analyze?pending_error=invalid_url (no ?job) home and unmounts the analyze layout/failure card", async () => {
    const history = createMemoryHistory();
    history.set({
      value: "/analyze?pending_error=invalid_url",
      scroll: false,
      replace: true,
    });
    render(() => (
      <MetaProvider>
        <MemoryRouter history={history}>
          <Route path="/analyze" component={AnalyzePage} />
          <Route
            path="/"
            component={() => <div data-testid="home-stub" />}
          />
        </MemoryRouter>
      </MetaProvider>
    ));
    await waitFor(() => {
      expect(screen.queryByTestId("home-stub")).not.toBeNull();
    });
    expect(screen.queryByTestId("analyze-layout")).toBeNull();
    expect(screen.queryByTestId("job-failure-card")).toBeNull();
  });

  it("retry wiring: clicking the production RetryButton on a failed slot triggers refetch and the done slot stays visible", async () => {
    retrySectionActionMock.mockResolvedValue({ ok: true });

    renderAt("/analyze?job=job-retry&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    const sections = {
      facts_claims__dedup: {
        state: "done",
        attempt_id: "attempt-done",
        data: {
          claims_report: {
            deduped_claims: [],
            total_claims: 0,
            total_unique: 0,
          },
        },
      },
      facts_claims__known_misinfo: {
        state: "failed",
        attempt_id: "attempt-failed",
        error: "boom",
      },
    };

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        sections: sections as unknown as JobState["sections"],
      }),
    );

    const retryBtn = await screen.findByTestId(
      "retry-facts_claims__known_misinfo",
    );
    expect(screen.queryByTestId("slot-facts_claims__dedup")).not.toBeNull();
    expect(
      screen
        .getByTestId("slot-facts_claims__dedup")
        .getAttribute("data-slot-state"),
    ).toBe("done");

    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(retrySectionActionMock).toHaveBeenCalledTimes(1);
    });
    const fd = retrySectionActionMock.mock.calls[0][0] as FormData;
    expect(fd.get("job_id")).toBe("job-retry");
    expect(fd.get("slug")).toBe("facts_claims__known_misinfo");

    await waitFor(() => {
      expect(refetchSpy.current).toHaveBeenCalledTimes(1);
    });

    expect(
      screen
        .getByTestId("slot-facts_claims__dedup")
        .getAttribute("data-slot-state"),
    ).toBe("done");
  });

  it("renders partial jobs like completed analysis with failed-section retry controls", async () => {
    renderAt("/analyze?job=job-partial&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "partial" as JobState["status"],
        error_code: "section_failure",
        error_message: "Sections failed: safety__web_risk",
        sections: {
          safety__moderation: {
            state: "done",
            attempt_id: "done-attempt",
            data: { harmful_content_matches: [] },
          },
          safety__web_risk: {
            state: "failed",
            attempt_id: "failed-attempt",
            error: "Google Web Risk rejected URI mailto:hn@ycombinator.com",
          },
        } as unknown as JobState["sections"],
      } as Partial<JobState>),
    );

    expect(await screen.findByTestId("analyze-layout")).not.toBeNull();
    expect(screen.queryByTestId("job-failure-card")).toBeNull();
    expect(screen.getByTestId("partial-failure-banner").textContent).toContain(
      "Web Risk",
    );
    expect(screen.getByTestId("retry-safety__web_risk")).toBeDefined();
  });

  it("changes the desktop analyze layout when preview size presets are selected", async () => {
    renderAt("/analyze?job=job-layout&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });

    const layout = screen.getByTestId("analyze-layout");
    expect(layout.getAttribute("data-preview-size")).toBe("regular");

    fireEvent.click(screen.getByRole("button", { name: "Large" }));
    expect(layout.getAttribute("data-preview-size")).toBe("large");

    fireEvent.click(screen.getByRole("button", { name: "Max width" }));
    expect(layout.getAttribute("data-preview-size")).toBe("max");
    expect(screen.getByTestId("analysis-sidebar")).not.toBeNull();
    expect(screen.getByTestId("analyze-main")).not.toBeNull();
  });

  it("widens the page max-width when Large is selected, not just the iframe-to-sidebar ratio", async () => {
    renderAt("/analyze?job=job-mainwidth&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });
    const analyzeMain = screen.getByTestId("analyze-main");
    expect(analyzeMain).not.toBeNull();

    const regularButton = screen.getByRole("button", { name: "Regular" });
    const largeButton = screen.getByRole("button", { name: "Large" });
    const maxButton = screen.getByRole("button", { name: "Max width" });
    const layout = screen.getByTestId("analyze-layout");
    expect(layout.getAttribute("data-preview-size")).toBe("regular");
    expect(regularButton.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(largeButton);
    expect(regularButton.getAttribute("aria-pressed")).toBe("false");
    expect(largeButton.getAttribute("aria-pressed")).toBe("true");
    expect(layout.getAttribute("data-preview-size")).toBe("large");

    fireEvent.click(maxButton);
    expect(largeButton.getAttribute("aria-pressed")).toBe("false");
    expect(maxButton.getAttribute("aria-pressed")).toBe("true");
    expect(layout.getAttribute("data-preview-size")).toBe("max");
  });

  it("uses grouped segmented controls with exclusive, press-state semantics", async () => {
    renderAt("/analyze?job=job-segmented&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("preview-mode-selector")).not.toBeNull();
    });

    const checkSegmentGroupingAndPressedState = async (
      groupTestId: string,
      labels: string[],
      options?: { interactive?: boolean },
    ) => {
      const group = screen.getByTestId(groupTestId);
      expect(group.getAttribute("role")).toBe("group");
      const buttons = labels.map(
        (label) => screen.getByRole("button", { name: label }) as HTMLElement,
      );
      // Sanity: all buttons live inside the same segmented group.
      for (const b of buttons) {
        expect(b.closest(`[role='group']`)).toBe(group);
      }
      await waitFor(() => {
        const pressedValues = buttons.map((button) =>
          button.getAttribute("aria-pressed"),
        );
        const pressedCount = pressedValues.filter(
          (pressed) => pressed === "true",
        ).length;

        expect(pressedCount).toBe(1);
        for (const pressed of pressedValues) {
          expect(["true", "false"]).toContain(pressed);
        }
      });

      if (options?.interactive !== true) return;

      fireEvent.click(buttons[0]);
      await waitFor(() => {
        expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
      });
      for (let i = 1; i < buttons.length; i += 1) {
        await waitFor(() => {
          expect(buttons[i].getAttribute("aria-pressed")).toBe("false");
        });
      }
      fireEvent.click(buttons[buttons.length - 1]);
      await waitFor(() => {
        expect(
          buttons[buttons.length - 1].getAttribute("aria-pressed"),
        ).toBe("true");
      });
      for (let i = 0; i < buttons.length - 1; i += 1) {
        await waitFor(() => {
          expect(buttons[i].getAttribute("aria-pressed")).toBe("false");
        });
      }
    };

    await checkSegmentGroupingAndPressedState("preview-mode-selector", [
      "Original",
      "Archived",
      "Screenshot",
    ]);
    await checkSegmentGroupingAndPressedState(
      "preview-size-selector",
      ["Regular", "Large", "Max width"],
      { interactive: true },
    );
  });

  it("keeps preview mode selections observable via aria-pressed across a blocked-to-unblocked job transition (TASK-1483.13.27)", async () => {
    const blockedCompat = frameCompatResult({
      canIframe: false,
      blockingHeader: "content-security-policy: frame-ancestors 'none'",
      cspFrameAncestors: "'none'",
      archivedPreviewUrl:
        "/api/archive-preview?url=https%3A%2F%2Fnypost.com%2Farticle",
    });
    const unblockedCompat = deferred<MockArchiveProbeResult>();

    getArchiveProbeMock
      .mockResolvedValueOnce(blockedCompat)
      .mockReturnValueOnce(unblockedCompat.promise);
    getScreenshotMock.mockResolvedValue(null);

    const history = renderAtWithHistory(
      "/analyze?job=task-1483.13.27&url=https://nypost.com/article",
    ).history;

    const archivedButton = await screen.findByTestId("preview-mode-archived");
    await waitFor(() => {
      expect(archivedButton.getAttribute("aria-pressed")).toBe("true");
    });
    const originalButton = screen.getByTestId("preview-mode-original");
    fireEvent.click(originalButton);
    await waitFor(() => {
      expect(originalButton.getAttribute("aria-pressed")).toBe("true");
    });
    expect(screen.getByTestId("analyze-main")).not.toBeNull();

    history.set({
      value:
        "/analyze?job=task-1483.13.27-unblocked&url=https://example.com/permissive",
      scroll: false,
      replace: true,
    });
    setPolledJobState(
      makeJobState({
        job_id: "task-1483.13.27-unblocked",
        status: "analyzing",
        url: "https://example.com/permissive",
      }),
    );

    expect(originalButton.getAttribute("aria-pressed")).toBe("true");
    expect(
      screen.getByTestId("preview-mode-archived").getAttribute("aria-pressed"),
    ).toBe("false");
    expect(
      screen.getByTestId("preview-mode-screenshot").getAttribute("aria-pressed"),
    ).toBe("false");

    unblockedCompat.resolve(
      frameCompatResult({
        canIframe: true,
        blockingHeader: null,
        cspFrameAncestors: null,
      }),
    );
    await waitFor(() => {
      expect(originalButton.getAttribute("aria-pressed")).toBe("true");
    });
  });

  it("renders preview mode selector alongside the width selector", async () => {
    renderAt("/analyze?job=job-preview-modes&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });

    expect(screen.getByTestId("preview-mode-selector")).not.toBeNull();
    expect(screen.getByTestId("preview-size-selector")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Original" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Archived" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Screenshot" })).not.toBeNull();
  });

  it("uses PDF preview URLs directly and skips archive and screenshot probes", async () => {
    const archiveUrl =
      "/api/archive-preview?source_type=pdf&job_id=job-pdf-preview";

    renderAt("/analyze?job=job-pdf-preview");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        job_id: "job-pdf-preview",
        status: "done",
        url: "pdfs/sample.pdf",
        source_type: "pdf",
        pdf_archive_url: archiveUrl,
      }),
    );

    // pdf_archive_url arriving auto-switches preview to Archived
    await waitFor(() => {
      expect(
        screen.getByTestId("page-frame-archived-iframe").getAttribute("src"),
      ).toBe(archiveUrl);
    });
    await flushMicrotasks();

    expect(screen.queryByTestId("page-frame-iframe")).toBeNull();
    expect(screen.queryByTestId("page-frame-pdf-embed")).toBeNull();
    expect(getArchiveProbeMock).not.toHaveBeenCalled();
    expect(getScreenshotMock).not.toHaveBeenCalled();
    expect(revalidateMock).not.toHaveBeenCalled();

    const screenshotButton = screen.getByTestId(
      "preview-mode-screenshot",
    ) as HTMLButtonElement;
    expect(screenshotButton.disabled).toBe(true);
    expect(screenshotButton.getAttribute("aria-label")).toBe(
      "Not available for PDFs",
    );

    // Archived button is active (auto-switched)
    const archivedButton = screen.getByTestId(
      "preview-mode-archived",
    ) as HTMLButtonElement;
    expect(archivedButton.disabled).toBe(false);
    expect(archivedButton.getAttribute("aria-pressed")).toBe("true");

    // Clicking Original returns to the PDF reader view
    fireEvent.click(screen.getByTestId("preview-mode-original"));
    await waitFor(() => {
      expect(
        screen.getByTestId("page-frame-pdf-object").getAttribute("data"),
      ).toBe("/api/pdf-read?job_id=job-pdf-preview");
    });
    expect(
      screen.getByTestId("page-frame-pdf-embed").getAttribute("src"),
    ).toBe("/api/pdf-read?job_id=job-pdf-preview");
  });

  it("returns to Original when a polling update resolves to PDF after Screenshot was selected", async () => {
    renderAt("/analyze?job=job-pdf-late");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByTestId("preview-mode-screenshot"));

    setPolledJobState(
      makeJobState({
        job_id: "job-pdf-late",
        status: "done",
        url: "pdfs/late.pdf",
        source_type: "pdf",
        pdf_archive_url: null,
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("page-frame-pdf-embed")).not.toBeNull();
    });

    const archivedButton = screen.getByTestId(
      "preview-mode-archived",
    ) as HTMLButtonElement;
    const screenshotButton = screen.getByTestId(
      "preview-mode-screenshot",
    ) as HTMLButtonElement;
    expect(archivedButton.disabled).toBe(true);
    expect(screenshotButton.disabled).toBe(true);
    expect(screenshotButton.getAttribute("aria-label")).toBe(
      "Not available for PDFs",
    );
    expect(
      screen.getByTestId("preview-mode-original").getAttribute("aria-pressed"),
    ).toBe("true");
    expect(screen.queryByTestId("page-frame-unavailable")).toBeNull();
    expect(getArchiveProbeMock).not.toHaveBeenCalled();
    expect(getScreenshotMock).not.toHaveBeenCalled();
  });

  it("keeps PDF Original visible and disables Archived when no pdf_archive_url is available", async () => {
    renderAt("/analyze?job=job-pdf-no-archive");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        job_id: "job-pdf-no-archive",
        status: "done",
        url: "pdfs/no-archive.pdf",
        source_type: "pdf",
        pdf_archive_url: null,
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("page-frame-pdf-embed")).not.toBeNull();
    });

    expect(
      (screen.getByTestId("preview-mode-archived") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(screen.queryByTestId("page-frame-archived-iframe")).toBeNull();
    expect(screen.queryByTestId("page-frame-unavailable")).toBeNull();
    expect(getArchiveProbeMock).not.toHaveBeenCalled();
    expect(getScreenshotMock).not.toHaveBeenCalled();
  });

  it("keeps preview size controls distinct from preview mode controls", async () => {
    renderAt("/analyze?job=job-preview-controls&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("preview-mode-selector")).not.toBeNull();
    });

    expect(screen.getByTestId("preview-mode-selector")).not.toBe(
      screen.getByTestId("preview-size-selector"),
    );
    expect(
      within(screen.getByTestId("preview-mode-selector")).getByRole("button", {
        name: "Original",
      }),
    ).not.toBeNull();
    expect(
      within(screen.getByTestId("preview-size-selector")).getByRole("button", {
        name: "Max width",
      }),
    ).not.toBeNull();
  });

  it("manual preview mode selection is session-scoped and resets for a new job", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: true,
        blockingHeader: null,
        cspFrameAncestors: null,
        archivedPreviewUrl:
          "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fa",
      }),
    );
    getScreenshotMock.mockResolvedValue("https://cdn.example.com/shot.png");

    renderAt("/analyze?job=job-preview-a&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });
    await waitFor(() => {
      expect(screen.queryByTestId("page-frame-loading")).toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: "Screenshot" }));
    expect(screen.getByRole("button", { name: "Screenshot" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(window.localStorage.getItem("vibecheck:preview-mode")).toBeNull();

    cleanup();
    pollingHandles.length = 0;
    renderAt("/analyze?job=job-preview-b&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Original" }).getAttribute("aria-pressed")).toBe(
        "true",
      );
    });
  });

  it("persists the preview size selection across analyze page remounts", async () => {
    renderAt("/analyze?job=job-layout&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Large" }));
    cleanup();
    pollingHandles.length = 0;

    renderAt("/analyze?job=job-layout&url=https://news.example.com/a");

    await waitFor(() => {
      expect(
        screen.getByTestId("analyze-layout").getAttribute("data-preview-size"),
      ).toBe("large");
    });
  });

  it("keeps the preview size selector visible at narrow viewports", async () => {
    renderAt("/analyze?job=job-layout&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("preview-size-selector")).not.toBeNull();
    });

    const selectorClass =
      screen.getByTestId("preview-size-selector").getAttribute("class") ?? "";
    expect(selectorClass).not.toContain("hidden");
    expect(selectorClass).not.toMatch(/(?:^|\s)hidden(?:\s|$)/);
    expect(selectorClass).not.toMatch(/lg:flex/);
  });

  it("can change the preview size at narrow widths without first widening the window", async () => {
    renderAt("/analyze?job=job-layout&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("preview-size-selector")).not.toBeNull();
    });

    const largeButton = screen.getByRole("button", { name: "Large" });
    fireEvent.click(largeButton);

    expect(largeButton.getAttribute("aria-pressed")).toBe("true");
    expect(
      screen.getByTestId("analyze-layout").getAttribute("data-preview-size"),
    ).toBe("large");
  });

  it("does not render CachedBadge when JobState.cached=false", async () => {
    renderAt("/analyze?job=job-fresh&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "done",
        cached: false,
      }),
    );

    expect(screen.queryByTestId("cached-badge")).toBeNull();
  });
});

describe("AnalyzePage left column min-h floor (TASK-1483.13.03)", () => {
  it("left column wrapper sizes to actual content", async () => {
    renderAt("/analyze?job=job-left-col&url=https://news.example.com/a");

    const leftColumn = await screen.findByTestId("analyze-left-column");
    expect(leftColumn).not.toBeNull();
    expect(screen.getByTestId("analysis-sidebar")).not.toBeNull();
  });
});

describe("AnalyzePage mobile analysis-first layout (TASK-1483.14.05)", () => {
  it("orders the analysis sidebar before the page preview on mobile and restores preview-left on desktop", async () => {
    renderAt("/analyze?job=job-mobile-order&url=https://news.example.com/a");

    const leftColumn = await screen.findByTestId("analyze-left-column");
    const sidebar = screen.getByTestId("analysis-sidebar");

    expect(
      leftColumn.compareDocumentPosition(sidebar) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0);
  });
});

describe("AnalyzePage archiveProbeState re-probe loop (TASK-1483.15.01)", () => {
  const url = "https://news.example.com/a";
  const archiveUrl = `/api/archive-preview?url=${encodeURIComponent(url)}`;
  const originalVisibilityDescriptor = Object.getOwnPropertyDescriptor(
    document,
    "visibilityState",
  );
  let visibilityState: DocumentVisibilityState = "visible";

  beforeEach(() => {
    vi.useFakeTimers();
    visibilityState = "visible";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibilityState,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalVisibilityDescriptor) {
      Object.defineProperty(
        document,
        "visibilityState",
        originalVisibilityDescriptor,
      );
    } else {
      delete (document as unknown as { visibilityState?: unknown })
        .visibilityState;
    }
  });

  const probeState = () =>
    screen
      .getByTestId("analyze-main")
      .getAttribute("data-archive-probe-state");

  it("archiveProbeState fires the first probe immediately and revalidates before each 5s probe", async () => {
    renderAt(`/analyze?job=job-archive-immediate&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();

    expect(getArchiveProbeMock).toHaveBeenCalledTimes(1);
    expect(getArchiveProbeMock).toHaveBeenNthCalledWith(
      1,
      url,
      "job-archive-immediate",
    );
    expect(revalidateMock).toHaveBeenNthCalledWith(
      1,
      `vibecheck-archive-probe:${url}:job-archive-immediate`,
    );
    expect(
      revalidateMock.mock.invocationCallOrder[0],
    ).toBeLessThan(getArchiveProbeMock.mock.invocationCallOrder[0]);
    expect(getScreenshotMock).toHaveBeenCalledTimes(1);
    expect(probeState()).toBe("pending");

    await vi.advanceTimersByTimeAsync(5_000);

    expect(getArchiveProbeMock).toHaveBeenCalledTimes(2);
    expect(revalidateMock).toHaveBeenNthCalledWith(
      2,
      `vibecheck-archive-probe:${url}:job-archive-immediate`,
    );
    expect(
      revalidateMock.mock.invocationCallOrder[1],
    ).toBeLessThan(getArchiveProbeMock.mock.invocationCallOrder[1]);
    expect(getScreenshotMock).toHaveBeenCalledTimes(1);
  });

  it("does not probe archive availability on pending-error failure pages", async () => {
    renderAt(
      `/analyze?pending_error=rate_limited&url=${encodeURIComponent(url)}`,
    );

    expect(await screen.findByTestId("job-failure-card")).not.toBeNull();
    await flushMicrotasks();
    await vi.advanceTimersByTimeAsync(300_000);

    expect(getArchiveProbeMock).not.toHaveBeenCalled();
    expect(getScreenshotMock).not.toHaveBeenCalled();
  });

  it("archiveProbeState stays pending until a later probe finds an archive, then becomes available", async () => {
    getArchiveProbeMock
      .mockResolvedValueOnce(
        frameCompatResult({
          canIframe: false,
          blockingHeader: "content-security-policy: frame-ancestors 'none'",
          cspFrameAncestors: "'none'",
          archivedPreviewUrl: null,
        }),
      )
      .mockResolvedValueOnce(
        frameCompatResult({
          canIframe: false,
          blockingHeader: "content-security-policy: frame-ancestors 'none'",
          cspFrameAncestors: "'none'",
          archivedPreviewUrl: archiveUrl,
        }),
      );
    getScreenshotMock.mockResolvedValue("https://cdn.example.com/shot.png");

    renderAt(`/analyze?job=job-archive-later&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();
    expect(probeState()).toBe("pending");

    await vi.advanceTimersByTimeAsync(5_000);

    expect(probeState()).toBe("available");
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
  });

  it("archiveProbeState becomes unavailable at the 300s wall-clock cap and stops probing", async () => {
    renderAt(`/analyze?job=job-archive-cap&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();
    expect(probeState()).toBe("pending");

    await vi.advanceTimersByTimeAsync(300_000);

    expect(probeState()).toBe("unavailable");
    const callsAtCap = getArchiveProbeMock.mock.calls.length;

    await vi.advanceTimersByTimeAsync(10_000);

    expect(getArchiveProbeMock).toHaveBeenCalledTimes(callsAtCap);
  });

  it("archiveProbeState enforces the 300s cap while a probe is still in flight", async () => {
    const hungProbe = deferred<MockArchiveProbeResult>();
    getArchiveProbeMock.mockReturnValueOnce(hungProbe.promise);

    renderAt(`/analyze?job=job-archive-hung&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(1);
    expect(probeState()).toBe("pending");

    await vi.advanceTimersByTimeAsync(300_000);

    expect(probeState()).toBe("unavailable");
    expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("archiveProbeState keeps a blocked no-screenshot page loading while archive availability is pending", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);

    renderAt(
      `/analyze?job=job-archive-pending-loading&url=${encodeURIComponent(url)}`,
    );
    await flushMicrotasks();

    expect(probeState()).toBe("pending");
    expect(screen.queryByTestId("page-frame-loading")).toBeNull();
    expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();

    await vi.advanceTimersByTimeAsync(300_000);

    expect(probeState()).toBe("unavailable");
    expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
  });

  it("archiveProbeState becomes unavailable after terminal status plus 10s grace", async () => {
    renderAt(`/analyze?job=job-archive-terminal&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();

    setPolledJobState(makeJobState({ status: "done", url }));
    await flushMicrotasks();

    await vi.advanceTimersByTimeAsync(9_999);
    expect(probeState()).toBe("pending");

    await vi.advanceTimersByTimeAsync(1);
    expect(probeState()).toBe("unavailable");
  });

  it("archiveProbeState performs a final probe at terminal grace before marking unavailable", async () => {
    getArchiveProbeMock
      .mockResolvedValueOnce(
        frameCompatResult({
          canIframe: false,
          blockingHeader: "content-security-policy: frame-ancestors 'none'",
          cspFrameAncestors: "'none'",
          archivedPreviewUrl: null,
        }),
      )
      .mockResolvedValueOnce(
        frameCompatResult({
          canIframe: false,
          blockingHeader: "content-security-policy: frame-ancestors 'none'",
          cspFrameAncestors: "'none'",
          archivedPreviewUrl: archiveUrl,
        }),
      );

    renderAt(`/analyze?job=job-archive-terminal-final&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();

    setPolledJobState(makeJobState({ status: "done", url }));
    await flushMicrotasks();

    await vi.advanceTimersByTimeAsync(10_000);

    expect(getArchiveProbeMock).toHaveBeenCalledTimes(2);
    expect(probeState()).toBe("available");
    expect(screen.getByTestId("page-frame-archived-iframe")).not.toBeNull();
  });

  it("archiveProbeState retries transient errors without marking unavailable", async () => {
    getArchiveProbeMock
      .mockResolvedValueOnce({ ok: false, kind: "transient_error" })
      .mockResolvedValueOnce(
        frameCompatResult({
          canIframe: false,
          blockingHeader: "content-security-policy: frame-ancestors 'none'",
          cspFrameAncestors: "'none'",
          archivedPreviewUrl: archiveUrl,
        }),
      );

    renderAt(`/analyze?job=job-archive-transient&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();

    expect(probeState()).toBe("pending");

    await vi.advanceTimersByTimeAsync(5_000);

    expect(getArchiveProbeMock).toHaveBeenCalledTimes(2);
    expect(probeState()).toBe("available");
  });

  it("archiveProbeState drops stale prior-generation probe responses silently", async () => {
    const oldProbe = deferred<MockArchiveProbeResult>();
    getArchiveProbeMock
      .mockReturnValueOnce(oldProbe.promise)
      .mockResolvedValueOnce(
        frameCompatResult({
          canIframe: false,
          blockingHeader: "content-security-policy: frame-ancestors 'none'",
          cspFrameAncestors: "'none'",
          archivedPreviewUrl:
            "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fb",
        }),
      );

    renderAt(`/analyze?job=job-archive-stale&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();

    setPolledJobState(makeJobState({ url: "https://news.example.com/b" }));
    await flushMicrotasks();

    oldProbe.resolve(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl:
          "/api/archive-preview?url=https%3A%2F%2Fnews.example.com%2Fold",
      }),
    );
    await flushMicrotasks();

    expect(probeState()).toBe("available");
    expect(
      screen
        .getByTestId("page-frame-archived-iframe")
        .getAttribute("src"),
    ).toContain("news.example.com%2Fb");
  });

  it("archiveProbeState pauses interval ticks while hidden and probes immediately when visible again", async () => {
    renderAt(`/analyze?job=job-archive-visibility&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(1);

    visibilityState = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(20_000);
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(1);

    visibilityState = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await flushMicrotasks();
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(4_999);
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(1);
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(3);
  });

  it("archiveProbeState does not recreate an interval when hidden-tab resume hits the 300s cap", async () => {
    renderAt(`/analyze?job=job-archive-hidden-cap&url=${encodeURIComponent(url)}`);
    await flushMicrotasks();
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(1);

    visibilityState = "hidden";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(300_000);
    expect(getArchiveProbeMock).toHaveBeenCalledTimes(1);

    visibilityState = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await flushMicrotasks();

    expect(probeState()).toBe("unavailable");
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("AnalyzePage headline summary mount (TASK-1483.13.10)", () => {
  it("does not render headline-summary before sidebarPayload arrives", async () => {
    renderAt("/analyze?job=job-headline-pending&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(makeJobState({ status: "analyzing" }));

    await waitFor(() => {
      expect(screen.queryByTestId("preview-mode-selector")).not.toBeNull();
    });
    expect(screen.queryByTestId("headline-summary")).toBeNull();
  });

  it("renders fallback headline text when sidebarPayload has headline=null", async () => {
    renderAt(
      "/analyze?job=job-headline-fallback&url=https://news.example.com/a",
    );

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        page_title: LONG_FALLBACK_HEADLINE_TITLE,
        sidebar_payload: makeSidebarPayload({ headline: null }),
        sidebar_payload_complete: true,
      }),
    );

    const headline = await screen.findByTestId("headline-summary");
    expect(headline.getAttribute("data-headline-source")).toBe("fallback");
    expect(screen.getByTestId("headline-summary-text").textContent).toBe(
      LONG_FALLBACK_HEADLINE_TEXT,
    );
  });

  it("renders real headline text when payload.headline.text is non-empty", async () => {
    renderAt("/analyze?job=job-headline-real&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        sidebar_payload: makeSidebarPayload({
          headline: {
            text: LONG_SERVER_HEADLINE_TEXT,
            kind: "synthesized",
            unavailable_inputs: [],
          },
        }),
        sidebar_payload_complete: true,
      }),
    );

    const headline = await screen.findByTestId("headline-summary");
    expect(headline.getAttribute("data-headline-source")).toBe("server");
    expect(screen.getByTestId("headline-summary-text").textContent).toBe(
      LONG_SERVER_HEADLINE_TEXT,
    );
  });

  it("places headline-summary before preview-mode-selector inside analyze-left-column", async () => {
    renderAt("/analyze?job=job-headline-order&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        sidebar_payload: makeSidebarPayload({
          headline: {
            text: "Headline appears above preview controls.",
            kind: "stock",
            unavailable_inputs: [],
          },
        }),
        sidebar_payload_complete: true,
      }),
    );

    const leftColumn = await screen.findByTestId("analyze-left-column");
    const headline = screen.getByTestId("headline-summary");
    const previewMode = screen.getByTestId("preview-mode-selector");

    expect(headline.closest("[data-testid='analyze-left-column']")).toBe(
      leftColumn,
    );
    expect(previewMode.closest("[data-testid='analyze-left-column']")).toBe(
      leftColumn,
    );
    expect(
      headline.compareDocumentPosition(previewMode) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("does not render headline summary when sidebar_payload_complete is false even if payload is present", async () => {
    renderAt("/analyze?job=job-partial-payload&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        sidebar_payload: makeSidebarPayload({
          headline: {
            text: "Should not appear yet",
            kind: "synthesized",
            unavailable_inputs: [],
          },
        }),
        sidebar_payload_complete: false,
      } as unknown as Partial<JobState>),
    );

    await waitFor(() => {
      expect(screen.queryByTestId("preview-mode-selector")).not.toBeNull();
    });
    expect(screen.queryByTestId("headline-summary")).toBeNull();
  });

  it("renders headline summary when sidebar_payload_complete is true", async () => {
    renderAt("/analyze?job=job-complete-payload&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "done",
        sidebar_payload: makeSidebarPayload({
          headline: {
            text: "Complete headline text.",
            kind: "synthesized",
            unavailable_inputs: [],
          },
        }),
        sidebar_payload_complete: true,
      } as unknown as Partial<JobState>),
    );

    const headline = await screen.findByTestId("headline-summary");
    expect(screen.getByTestId("headline-summary-text").textContent).toBe(
      "Complete headline text.",
    );
    expect(headline.getAttribute("data-headline-source")).toBe("server");
  });

  it("does not render cached badge when cached=true but sidebar_payload_complete is false", async () => {
    renderAt("/analyze?job=job-partial-cache&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        cached: true,
        sidebar_payload: makeSidebarPayload(),
        sidebar_payload_complete: false,
      } as unknown as Partial<JobState>),
    );

    await waitFor(() => {
      expect(screen.queryByTestId("preview-mode-selector")).not.toBeNull();
    });
    expect(screen.queryByTestId("cached-badge")).toBeNull();
  });

  it("renders cached badge when cached=true and sidebar_payload_complete is true", async () => {
    renderAt("/analyze?job=job-complete-cache&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "done",
        cached: true,
        sidebar_payload: makeSidebarPayload({
          cached_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
        }),
        sidebar_payload_complete: true,
      } as unknown as Partial<JobState>),
    );

    const badge = await screen.findByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
  });
});

describe("AnalyzePage Archived tab availability (TASK-1483.15.02)", () => {
  const url = "https://news.example.com/a";

  function getPreviewModeButton(mode: "original" | "archived" | "screenshot") {
    return screen.getByTestId(`preview-mode-${mode}`) as HTMLButtonElement;
  }

  function mockBlockedNoFallbacks() {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);
  }

  it("keeps Archived enabled without a title while archiveProbeState is pending", async () => {
    vi.useFakeTimers();
    mockBlockedNoFallbacks();

    try {
      renderAt(
        `/analyze?job=job-archive-pending-tab&url=${encodeURIComponent(url)}`,
      );
      await flushMicrotasks();

      const archived = getPreviewModeButton("archived");
      expect(screen.queryByTestId("page-frame-loading")).toBeNull();
      expect(
        screen
          .getByTestId("analyze-main")
          .getAttribute("data-archive-probe-state"),
      ).toBe("pending");
      expect(archived.disabled).toBe(false);
      expect(archived.hasAttribute("disabled")).toBe(false);
      expect(archived.hasAttribute("title")).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps Archived enabled without a title while archiveProbeState is available", async () => {
    const archiveUrl = `/api/archive-preview?url=${encodeURIComponent(url)}`;
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: archiveUrl,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);

    renderAt(
      `/analyze?job=job-archive-available-tab&url=${encodeURIComponent(url)}`,
    );
    await flushMicrotasks();

    const archived = getPreviewModeButton("archived");
    expect(
      screen
        .getByTestId("analyze-main")
        .getAttribute("data-archive-probe-state"),
    ).toBe("available");
    expect(archived.disabled).toBe(false);
    expect(archived.hasAttribute("disabled")).toBe(false);
    expect(archived.hasAttribute("title")).toBe(false);

    fireEvent.click(archived);
    expect(archived.getAttribute("aria-pressed")).toBe("true");
  });

  it("disables Archived with a title when archiveProbeState is unavailable without affecting Original or Screenshot", async () => {
    vi.useFakeTimers();
    mockBlockedNoFallbacks();

    try {
      renderAt(
        `/analyze?job=job-archive-unavailable-tab&url=${encodeURIComponent(url)}`,
      );
      await flushMicrotasks();

      setPolledJobState(makeJobState({ status: "done", url }));
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(10_000);

      const original = getPreviewModeButton("original");
      const archived = getPreviewModeButton("archived");
      const screenshot = getPreviewModeButton("screenshot");

      expect(
        screen
          .getByTestId("analyze-main")
          .getAttribute("data-archive-probe-state"),
      ).toBe("unavailable");
      expect(archived.disabled).toBe(true);
      expect(archived.getAttribute("title")).toBe(
        "No archive available for this page",
      );
      expect(archived.getAttribute("aria-pressed")).toBe("false");

      expect(original.disabled).toBe(false);
      expect(original.hasAttribute("title")).toBe(false);
      expect(screenshot.disabled).toBe(false);
      expect(screenshot.hasAttribute("title")).toBe(false);

      fireEvent.click(archived);
      expect(archived.getAttribute("aria-pressed")).toBe("false");
      expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("AnalyzePage utterance refs", () => {
  const url = "https://news.example.com/a";
  const archiveUrl = `/api/archive-preview?url=${encodeURIComponent(url)}&job_id=job-utterance-scroll`;

  function jobWithFlashpoint(
    overrides: Pick<Partial<SidebarPayload>, "utterances"> = {},
  ): JobState {
    return makeJobState({
      job_id: "job-utterance-scroll",
      status: "done",
      url,
      sidebar_payload: makeSidebarPayload({
        utterances: [
          {
            position: 1,
            utterance_id: "comment-0-aaa",
          },
        ],
        tone_dynamics: {
          scd: {
            narrative: "",
            summary: "",
            tone_labels: [],
            per_speaker_notes: {},
            insufficient_conversation: true,
          },
          flashpoint_matches: [
            {
              scan_type: "conversation_flashpoint",
              utterance_id: "comment-0-aaa",
              derailment_score: 64,
              risk_level: "Heated",
              reasoning: "rising tension",
              context_messages: 2,
            },
          ],
        },
        ...overrides,
      }),
    });
  }

  it("queues a ref click from Original mode and scrolls after the archived iframe loads", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: true,
        archivedPreviewUrl: archiveUrl,
      }),
    );
    renderAt(
      `/analyze?job=job-utterance-scroll&url=${encodeURIComponent(url)}`,
    );
    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });
    setPolledJobState(jobWithFlashpoint());
    await flushMicrotasks();

    fireEvent.click(await screen.findByTestId("flashpoint-utterance-ref"));
    await waitFor(() => {
      expect(
        screen.getByTestId("preview-mode-archived").getAttribute("aria-pressed"),
      ).toBe("true");
    });
    expect(scrollToUtteranceMock).not.toHaveBeenCalled();

    const archived = screen.getByTestId(
      "page-frame-archived-iframe",
    ) as HTMLIFrameElement;
    Object.defineProperty(archived, "contentDocument", {
      configurable: true,
      value: document.implementation.createHTMLDocument("Archived"),
    });
    archived.contentDocument?.body.append(document.createElement("p"));
    archived.dispatchEvent(new Event("load"));

    await waitFor(() => {
      expect(scrollToUtteranceMock).toHaveBeenCalledWith(
        archived,
        "comment-0-aaa",
        expect.objectContaining({ lastHighlightedId: null }),
      );
    });
  });

  it("renders utterance refs disabled when no archive URL is available", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: true,
        archivedPreviewUrl: null,
      }),
    );
    renderAt(`/analyze?job=job-no-archive&url=${encodeURIComponent(url)}`);
    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });
    setPolledJobState(jobWithFlashpoint());
    await flushMicrotasks();

    expect(
      (await screen.findByTestId("flashpoint-utterance-ref")).getAttribute(
        "aria-disabled",
      ),
    ).toBe("true");
  });

  it("renders utterance refs disabled when the current job has no archive anchors", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: true,
        archivedPreviewUrl: archiveUrl,
      }),
    );
    renderAt(
      `/analyze?job=job-utterance-scroll&url=${encodeURIComponent(url)}`,
    );
    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });
    setPolledJobState(jobWithFlashpoint({ utterances: [] }));
    await flushMicrotasks();

    const ref = await screen.findByTestId("flashpoint-utterance-ref");
    expect(ref.getAttribute("aria-disabled")).toBe("true");

    fireEvent.click(ref);

    expect(scrollToUtteranceMock).not.toHaveBeenCalled();
    expect(
      screen.getByTestId("preview-mode-archived").getAttribute("aria-pressed"),
    ).toBe("false");
  });
});

describe("AnalyzePage Original tab — soft-disabled when canIframe=false (TASK-1483.13.02)", () => {
  function mockBlockedFrame() {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl:
          "/api/archive-preview?url=https%3A%2F%2Fnypost.com%2Farticle",
      }),
    );
    getScreenshotMock.mockResolvedValue("https://cdn.example.com/shot.png");
  }

  it("renders an aria-describedby tooltip on Original when the page blocks framing", async () => {
    mockBlockedFrame();
    renderAt("/analyze?job=job-blocked&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      expect(original.getAttribute("aria-describedby")).toBe(
        "preview-mode-original-tip",
      );
    });

    const tip = screen.getByTestId("preview-mode-original-tip");
    expect(tip.getAttribute("id")).toBe("preview-mode-original-tip");
    expect(tip.textContent ?? "").toMatch(
      /blocks framing.*click to attempt anyway/i,
    );
    expect((tip.getAttribute("class") ?? "").split(/\s+/)).toContain("sr-only");
    expect(tip.getAttribute("role")).toBe("tooltip");
    expect(tip.getAttribute("data-visible")).toBe("false");
  });

  it("surfaces the Original blocked-frame tooltip on hover and focus", async () => {
    mockBlockedFrame();
    renderAt("/analyze?job=job-blocked&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      expect(original.getAttribute("aria-describedby")).toBe(
        "preview-mode-original-tip",
      );
    });

    const tip = screen.getByTestId("preview-mode-original-tip");
    expect(tip.getAttribute("role")).toBe("tooltip");
    expect(tip.getAttribute("data-visible")).toBe("false");

    fireEvent.mouseEnter(original);
    expect(tip.getAttribute("data-visible")).toBe("true");
    expect(tip.textContent ?? "").toMatch(
      /blocks framing.*click to attempt anyway/i,
    );

    fireEvent.mouseLeave(original);
    expect(tip.getAttribute("data-visible")).toBe("false");

    fireEvent.focus(original);
    expect(tip.getAttribute("data-visible")).toBe("true");
  });

  it("keeps the Original blocked-frame tooltip visible after mouse leave while focused", async () => {
    mockBlockedFrame();
    renderAt("/analyze?job=job-blocked&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      expect(original.getAttribute("aria-describedby")).toBe(
        "preview-mode-original-tip",
      );
    });

    const tip = screen.getByRole("tooltip");

    fireEvent.focus(original);
    expect(tip.getAttribute("data-visible")).toBe("true");

    fireEvent.mouseLeave(original);
    expect(tip.getAttribute("data-visible")).toBe("true");

    fireEvent.blur(original);
    expect(tip.getAttribute("data-visible")).toBe("false");
  });

  it("describes Original when canIframe=false without disabling it", async () => {
    mockBlockedFrame();
    renderAt("/analyze?job=job-blocked&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      expect(original.getAttribute("aria-describedby")).toBe(
        "preview-mode-original-tip",
      );
    });
    // AC #4: must NOT use aria-disabled, disabled, or pointer-events:none.
    expect(original.hasAttribute("aria-disabled")).toBe(false);
    expect(original.hasAttribute("disabled")).toBe(false);
    expect(original.getAttribute("class") ?? "").not.toMatch(
      /pointer-events-none/,
    );
  });

  it("Original tab remains clickable as the escape hatch when canIframe=false", async () => {
    mockBlockedFrame();
    renderAt("/analyze?job=job-blocked&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      // Auto-resolve flips the parent's previewMode off Original.
      expect(original.getAttribute("aria-pressed")).toBe("false");
    });
    fireEvent.click(original);
    expect(original.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("page-frame-deciding")).not.toBeNull();
  });

  it("does not show Original pressed before frame compatibility resolves", async () => {
    const pendingCompat = deferred<MockArchiveProbeResult>();
    getArchiveProbeMock.mockReturnValueOnce(pendingCompat.promise);
    getScreenshotMock.mockResolvedValue("https://cdn.example.com/shot.png");

    renderAt("/analyze?job=job-pending-compat&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    expect(original.getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByTestId("page-frame-loading")).toBeNull();
    expect(screen.getByTestId("page-frame-iframe")).not.toBeNull();

    pendingCompat.resolve(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        screenshotUrl: "https://cdn.example.com/shot.png",
        archivedPreviewUrl:
          "/api/archive-preview?url=https%3A%2F%2Fnypost.com%2Farticle",
      }),
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("preview-mode-archived").getAttribute("aria-pressed"),
      ).toBe("true");
    });
    expect(original.getAttribute("aria-pressed")).toBe("false");
  });

  it("clears the Original blocked-frame tooltip from any preview tab leave or blur", async () => {
    mockBlockedFrame();
    renderAt(
      "/analyze?job=job-blocked-tooltip-clear&url=https://nypost.com/article",
    );

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      expect(original.getAttribute("aria-describedby")).toBe(
        "preview-mode-original-tip",
      );
    });
    const archived = screen.getByTestId("preview-mode-archived");
    const tip = screen.getByTestId("preview-mode-original-tip");

    fireEvent.mouseEnter(original);
    expect(tip.getAttribute("data-visible")).toBe("true");
    fireEvent.mouseLeave(archived);
    expect(tip.getAttribute("data-visible")).toBe("false");

    fireEvent.focus(original);
    expect(tip.getAttribute("data-visible")).toBe("true");
    fireEvent.blur(archived);
    expect(tip.getAttribute("data-visible")).toBe("false");
  });

  it("clears pressed preview state when a resolvable preview transitions to unavailable", async () => {
    vi.useFakeTimers();
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock
      .mockResolvedValueOnce("https://cdn.example.com/first.png")
      .mockResolvedValueOnce(null);

    try {
      renderAt(
        "/analyze?job=job-preview-transition&url=https://news.example.com/a",
      );
      await flushMicrotasks();

      expect(
        screen
          .getByTestId("preview-mode-screenshot")
          .getAttribute("aria-pressed"),
      ).toBe("true");

      setPolledJobState(
        makeJobState({
          status: "done",
          url: "https://news.example.com/b",
        }),
      );
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(10_000);

      expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
      for (const testId of [
        "preview-mode-original",
        "preview-mode-archived",
        "preview-mode-screenshot",
      ]) {
        expect(screen.getByTestId(testId).getAttribute("aria-pressed")).toBe(
          "false",
        );
      }
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears all preview tab pressed states when no preview is available", async () => {
    vi.useFakeTimers();
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);
    try {
      renderAt("/analyze?job=job-unavailable&url=https://nypost.com/article");
      await flushMicrotasks();

      setPolledJobState(
        makeJobState({ status: "done", url: "https://nypost.com/article" }),
      );
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(10_000);

      expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
      for (const testId of [
        "preview-mode-original",
        "preview-mode-archived",
        "preview-mode-screenshot",
      ]) {
        expect(screen.getByTestId(testId).getAttribute("aria-pressed")).toBe(
          "false",
        );
      }
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps all preview tabs unpressed when clicking the requested tab while preview is unavailable", async () => {
    vi.useFakeTimers();
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);
    try {
      renderAt("/analyze?job=job-unavailable&url=https://nypost.com/article");
      await flushMicrotasks();

      setPolledJobState(
        makeJobState({ status: "done", url: "https://nypost.com/article" }),
      );
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(10_000);

      expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();

      fireEvent.click(screen.getByTestId("preview-mode-original"));

      expect(screen.getByTestId("page-frame-unavailable")).not.toBeNull();
      for (const testId of [
        "preview-mode-original",
        "preview-mode-archived",
        "preview-mode-screenshot",
      ]) {
        expect(screen.getByTestId(testId).getAttribute("aria-pressed")).toBe(
          "false",
        );
      }
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not render the tooltip span when canIframe=true", async () => {
    // default mock returns canIframe: true
    renderAt("/analyze?job=job-permissive&url=https://news.example.com/a");

    const original = await screen.findByTestId("preview-mode-original");
    expect(original.getAttribute("aria-describedby")).toBeNull();
    expect(screen.queryByTestId("preview-mode-original-tip")).toBeNull();
  });

  it("createAsync 404: getJobState rejection does not bubble to root ErrorBoundary", async () => {
    getJobStateMock.mockRejectedValueOnce(
      new Error("vibecheck GET /api/analyze/stale-job-id failed: 404"),
    );

    const history = createMemoryHistory();
    history.set({
      value: "/analyze?job=stale-job-id&c=1",
      scroll: false,
      replace: true,
    });
    render(() => (
      <MetaProvider>
        <ErrorBoundary
          fallback={(err) => (
            <div data-testid="root-error-boundary">
              Something went wrong: {err.message}
            </div>
          )}
        >
          <MemoryRouter history={history}>
            <Route path="/analyze" component={AnalyzePage} />
          </MemoryRouter>
        </ErrorBoundary>
      </MetaProvider>
    ));

    expect(await screen.findByTestId("analyze-layout")).not.toBeNull();
    expect(screen.queryByTestId("root-error-boundary")).toBeNull();
  });

  describe("expired analysis card", () => {
    beforeEach(() => {
      pollingHandles.length = 0;
    });
    afterEach(() => cleanup());

    it("renders ExpiredAnalysisCard when jobState has expired_at set", async () => {
      renderAt("/analyze?job=expired-job-id&url=https://example.com/article");
      await flushMicrotasks();
      setPolledJobState({
        job_id: "expired-job-id",
        url: "https://example.com/article",
        status: "done",
        attempt_id: "attempt-1",
        error_code: null,
        error_message: null,
        source_type: "url",
        created_at: "2026-04-28T00:00:00Z",
        updated_at: "2026-04-28T00:00:00Z",
        cached: false,
        expired_at: "2026-04-28T10:00:00Z",
        sidebar_payload: null,
        sidebar_payload_complete: false,
        sections: {},
        next_poll_ms: 1500,
        utterance_count: 0,
      } as unknown as JobState);
      expect(await screen.findByTestId("expired-analysis-card")).not.toBeNull();
      expect(screen.queryByTestId("job-failure-card")).toBeNull();
      expect(screen.queryByTestId("analyze-layout")).toBeNull();
    });

    it("renders ExpiredAnalysisCard when polling 404 AND searchParams has url=", async () => {
      renderAt("/analyze?job=old-job-id&c=1&url=https%3A%2F%2Fexample.com%2Farticle");
      await flushMicrotasks();
      const handle = pollingHandles[pollingHandles.length - 1];
      const err = Object.assign(new Error("not found"), { statusCode: 404 });
      handle.setError(err);
      expect(await screen.findByTestId("expired-analysis-card")).not.toBeNull();
      expect(screen.queryByTestId("job-failure-card")).toBeNull();
    });

    it("renders JobFailureCard (NOT expired card) when polling 404 but no searchParams.url", async () => {
      renderAt("/analyze?job=old-job-id&c=1");
      await flushMicrotasks();
      const handle = pollingHandles[pollingHandles.length - 1];
      const err = Object.assign(new Error("not found"), { statusCode: 404 });
      handle.setError(err);
      expect(await screen.findByTestId("job-failure-card")).not.toBeNull();
      expect(screen.queryByTestId("expired-analysis-card")).toBeNull();
    });

    it("renders JobFailureCard (NOT expired card) when polling 5xx", async () => {
      renderAt("/analyze?job=error-job-id&c=1&url=https://example.com/a");
      await flushMicrotasks();
      const handle = pollingHandles[pollingHandles.length - 1];
      const err = Object.assign(new Error("server error"), { statusCode: 500 });
      handle.setError(err);
      expect(await screen.findByTestId("job-failure-card")).not.toBeNull();
      expect(screen.queryByTestId("expired-analysis-card")).toBeNull();
    });

    it("renders JobFailureCard (NOT expired card) for a failed job without expired_at", async () => {
      renderAt("/analyze?job=failed-job-id");
      await flushMicrotasks();
      setPolledJobState({
        job_id: "failed-job-id",
        url: "https://example.com/article",
        status: "failed",
        attempt_id: "attempt-1",
        error_code: "upstream_error",
        error_message: "upstream failed",
        source_type: "url",
        created_at: "2026-04-28T00:00:00Z",
        updated_at: "2026-04-28T00:00:00Z",
        cached: false,
        expired_at: null,
        sidebar_payload: null,
        sidebar_payload_complete: false,
        sections: {},
        next_poll_ms: 1500,
        utterance_count: 0,
      } as unknown as JobState);
      expect(await screen.findByTestId("job-failure-card")).not.toBeNull();
      const card = screen.getByTestId("job-failure-card");
      expect(card.getAttribute("data-error-code")).toBe("upstream_error");
      expect(screen.queryByTestId("expired-analysis-card")).toBeNull();
    });
  });
});
