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
} from "@solidjs/testing-library";
import { MetaProvider } from "@solidjs/meta";
import {
  MemoryRouter,
  Route,
  createMemoryHistory,
} from "@solidjs/router";
import { createSignal } from "solid-js";
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
) => Promise<MockArchiveProbeResult>;

type GetScreenshotMock = (url: string) => Promise<string | null>;

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
    createPollingResource: () => {
      const [state, setState] = createSignal<JobState | null>(null);
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
    keyFor: (url: string) => `vibecheck-archive-probe:${url}`,
    key: "vibecheck-archive-probe",
  });
  const getScreenshotStub = Object.assign(getScreenshotMock, {
    keyFor: (url: string) => `vibecheck-screenshot:${url}`,
    key: "vibecheck-screenshot",
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
    getScreenshot: getScreenshotStub,
    retrySectionAction: retryStub,
    analyzeAction: analyzeActionStub,
    pollJobState: pollStub,
  };
});

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
  revalidateMock.mockReset();
  revalidateMock.mockImplementation(async () => undefined);
  window.localStorage.clear();
  pollingHandles.length = 0;
  refetchSpy.current.mockReset();
  retrySectionActionMock.mockReset();
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
  await Promise.resolve();
  await Promise.resolve();
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

  it("renders CachedBadge with a timestamp when JobState.cached=true and sidebar_payload.cached_at is set (even if payload.cached is false)", async () => {
    renderAt("/analyze?job=job-cache&c=1&url=https://news.example.com/a");

    await waitFor(() => {
      expect(pollingHandles.length).toBeGreaterThan(0);
    });

    setPolledJobState(
      makeJobState({
        status: "done",
        cached: true,
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
    expect(layout.getAttribute("class")).toContain(
      "lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]",
    );

    fireEvent.click(screen.getByRole("button", { name: "Large" }));
    expect(layout.getAttribute("data-preview-size")).toBe("large");
    expect(layout.getAttribute("class")).toContain(
      "lg:grid-cols-[minmax(0,5fr)_minmax(0,2fr)]",
    );

    fireEvent.click(screen.getByRole("button", { name: "Max width" }));
    expect(layout.getAttribute("data-preview-size")).toBe("max");
    expect(layout.getAttribute("class")).toContain("lg:grid-cols-1");
    expect(screen.getByTestId("analysis-sidebar")).not.toBeNull();
  });

  it("widens the page max-width when Large is selected, not just the iframe-to-sidebar ratio", async () => {
    renderAt("/analyze?job=job-mainwidth&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("analyze-layout")).not.toBeNull();
    });

    const main = document.querySelector("main") as HTMLElement;
    expect(main).not.toBeNull();
    const regularClass = main.getAttribute("class") ?? "";
    expect(regularClass).toContain("max-w-6xl");

    fireEvent.click(screen.getByRole("button", { name: "Large" }));
    const largeClass = main.getAttribute("class") ?? "";
    expect(largeClass).not.toContain("max-w-6xl");
    expect(largeClass).toMatch(/max-w-\[/);

    fireEvent.click(screen.getByRole("button", { name: "Max width" }));
    const maxClass = main.getAttribute("class") ?? "";
    expect(maxClass).toMatch(/max-w-\[/);
  });

  it("uses outer-corners-only rounding on segmented controls so selected/hover does not show a half-rounded artifact", async () => {
    renderAt("/analyze?job=job-segmented&url=https://news.example.com/a");

    await waitFor(() => {
      expect(screen.queryByTestId("preview-mode-selector")).not.toBeNull();
    });

    const checkSegmentRounding = (groupTestId: string, labels: string[]) => {
      const buttons = labels.map(
        (label) => screen.getByRole("button", { name: label }) as HTMLElement,
      );
      // Sanity: all buttons live inside the same segmented group.
      for (const b of buttons) {
        expect(b.closest(`[data-testid='${groupTestId}']`)).not.toBeNull();
      }
      // None of the segment buttons should have plain `rounded-md` — that's the bug.
      for (const b of buttons) {
        const cls = b.getAttribute("class") ?? "";
        expect(cls).not.toMatch(/(?:^|\s)rounded-md(?:\s|$)/);
      }
      const first = buttons[0].getAttribute("class") ?? "";
      const last = buttons[buttons.length - 1].getAttribute("class") ?? "";
      expect(first).toMatch(/rounded-l-md/);
      expect(last).toMatch(/rounded-r-md/);
      for (let i = 1; i < buttons.length - 1; i++) {
        const mid = buttons[i].getAttribute("class") ?? "";
        expect(mid).toMatch(/rounded-none/);
      }
    };

    checkSegmentRounding("preview-mode-selector", [
      "Original",
      "Archived",
      "Screenshot",
    ]);
    checkSegmentRounding("preview-size-selector", [
      "Regular",
      "Large",
      "Max width",
    ]);
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
  it("left column wrapper does not enforce min-h-[60vh] so it sizes to actual content", async () => {
    renderAt("/analyze?job=job-left-col&url=https://news.example.com/a");

    const leftColumn = await screen.findByTestId("analyze-left-column");
    const cls = leftColumn.getAttribute("class") ?? "";
    expect(cls).not.toMatch(/min-h-\[60vh\]/);
    // Sanity: surrounding flex/min-w invariants preserved.
    expect(cls).toMatch(/\bflex\b/);
    expect(cls).toMatch(/\bmin-w-0\b/);
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
    expect(getArchiveProbeMock).toHaveBeenNthCalledWith(1, url);
    expect(revalidateMock).toHaveBeenNthCalledWith(
      1,
      `vibecheck-archive-probe:${url}`,
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
      `vibecheck-archive-probe:${url}`,
    );
    expect(
      revalidateMock.mock.invocationCallOrder[1],
    ).toBeLessThan(getArchiveProbeMock.mock.invocationCallOrder[1]);
    expect(getScreenshotMock).toHaveBeenCalledTimes(1);
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
        page_title: "Investigative dispatch",
        sidebar_payload: makeSidebarPayload({ headline: null }),
      }),
    );

    const headline = await screen.findByTestId("headline-summary");
    expect(headline.getAttribute("data-headline-source")).toBe("fallback");
    expect(screen.getByTestId("headline-summary-text").textContent).toBe(
      "news.example.com — Investigative dispatch",
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
            text: "Verified article headline from the analysis payload.",
            kind: "synthesized",
            unavailable_inputs: [],
          },
        }),
      }),
    );

    const headline = await screen.findByTestId("headline-summary");
    expect(headline.getAttribute("data-headline-source")).toBe("server");
    expect(screen.getByTestId("headline-summary-text").textContent).toBe(
      "Verified article headline from the analysis payload.",
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

  it("uses muted opacity styling on Original when canIframe=false (no aria-disabled, no disabled attr)", async () => {
    mockBlockedFrame();
    renderAt("/analyze?job=job-blocked&url=https://nypost.com/article");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      const cls = original.getAttribute("class") ?? "";
      expect(cls).toMatch(/opacity-60/);
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
    expect(original.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByTestId("page-frame-loading")).not.toBeNull();

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
          archivedPreviewUrl: null,
        }),
      );
    getScreenshotMock
      .mockResolvedValueOnce("https://cdn.example.com/first.png")
      .mockResolvedValueOnce(null);

    renderAt(
      "/analyze?job=job-preview-transition&url=https://news.example.com/a",
    );

    await waitFor(() => {
      expect(
        screen
          .getByTestId("preview-mode-screenshot")
          .getAttribute("aria-pressed"),
      ).toBe("true");
    });

    setPolledJobState(
      makeJobState({
        status: "analyzing",
        url: "https://news.example.com/b",
      }),
    );

    expect(await screen.findByTestId("page-frame-unavailable")).not.toBeNull();
    for (const testId of [
      "preview-mode-original",
      "preview-mode-archived",
      "preview-mode-screenshot",
    ]) {
      expect(screen.getByTestId(testId).getAttribute("aria-pressed")).toBe(
        "false",
      );
    }
  });

  it("clears all preview tab pressed states when no preview is available", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);
    renderAt("/analyze?job=job-unavailable&url=https://nypost.com/article");

    expect(await screen.findByTestId("page-frame-unavailable")).not.toBeNull();

    for (const testId of [
      "preview-mode-original",
      "preview-mode-archived",
      "preview-mode-screenshot",
    ]) {
      expect(screen.getByTestId(testId).getAttribute("aria-pressed")).toBe(
        "false",
      );
    }
  });

  it("keeps all preview tabs unpressed when clicking the requested tab while preview is unavailable", async () => {
    getArchiveProbeMock.mockResolvedValue(
      frameCompatResult({
        canIframe: false,
        blockingHeader: "content-security-policy: frame-ancestors 'none'",
        cspFrameAncestors: "'none'",
        archivedPreviewUrl: null,
      }),
    );
    getScreenshotMock.mockResolvedValue(null);
    renderAt("/analyze?job=job-unavailable&url=https://nypost.com/article");

    expect(await screen.findByTestId("page-frame-unavailable")).not.toBeNull();

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
  });

  it("does not render the tooltip span or the muted styling when canIframe=true", async () => {
    // default mock returns canIframe: true
    renderAt("/analyze?job=job-permissive&url=https://news.example.com/a");

    const original = await screen.findByTestId("preview-mode-original");
    await waitFor(() => {
      expect(original.getAttribute("class") ?? "").not.toMatch(/opacity-60/);
    });
    expect(original.getAttribute("aria-describedby")).toBeNull();
    expect(screen.queryByTestId("preview-mode-original-tip")).toBeNull();
  });
});
