import { describe, it, expect, vi, afterEach } from "vitest";
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
import type { JobState } from "~/lib/api-client.server";

type PollingHandle = {
  state: () => JobState | null;
  error: () => Error | null;
  refetch: () => void;
};

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

const { retrySectionActionMock } = vi.hoisted(() => ({
  retrySectionActionMock: vi.fn(),
}));

vi.mock("@solidjs/router", async () => {
  const actual = await vi.importActual<typeof import("@solidjs/router")>(
    "@solidjs/router",
  );
  return {
    ...actual,
    useAction: (action: unknown) => {
      void action;
      return retrySectionActionMock;
    },
  };
});

vi.mock("~/routes/analyze.data", () => {
  const getFrameCompatStub = Object.assign(
    vi.fn(async () => ({
      ok: true,
      frameCompat: {
        canIframe: true,
        blockingHeader: null,
        screenshotUrl: null,
      },
    })),
    {
      keyFor: () => "vibecheck-frame-compat",
      key: "vibecheck-frame-compat",
    },
  );
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
    getFrameCompat: getFrameCompatStub,
    retrySectionAction: retryStub,
    analyzeAction: analyzeActionStub,
    pollJobState: pollStub,
  };
});

import AnalyzePage from "../../src/routes/analyze";

afterEach(() => {
  cleanup();
  pollingHandles.length = 0;
  refetchSpy.current.mockReset();
  retrySectionActionMock.mockReset();
});

function setPolledJobState(value: JobState | null) {
  for (const h of pollingHandles) h.setState(value);
}

function renderAt(path: string) {
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
