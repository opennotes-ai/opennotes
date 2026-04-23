import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@solidjs/testing-library";
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

const { pollingHandles } = vi.hoisted(() => ({
  pollingHandles: [] as Array<{
    setState: (v: JobState | null) => void;
    setError: (v: Error | null) => void;
    handle: PollingHandle;
  }>,
}));

vi.mock("~/lib/polling", () => {
  return {
    createPollingResource: () => {
      const [state, setState] = createSignal<JobState | null>(null);
      const [error, setError] = createSignal<Error | null>(null);
      const handle: PollingHandle = {
        state,
        error,
        refetch: () => {},
      };
      pollingHandles.push({ setState, setError, handle });
      return handle;
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
  const pollStub = Object.assign(vi.fn(), {
    keyFor: () => "vibecheck-poll-job",
    key: "vibecheck-poll-job",
  });
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

  it("when no ?job is present, falls back to the pending_error URL param", async () => {
    renderAt(
      "/analyze?pending_error=unsupported_site&url=https://blocked.example.com&host=blocked.example.com",
    );

    const failureCard = await screen.findByTestId("job-failure-card");
    expect(failureCard.getAttribute("data-error-code")).toBe(
      "unsupported_site",
    );
  });
});
