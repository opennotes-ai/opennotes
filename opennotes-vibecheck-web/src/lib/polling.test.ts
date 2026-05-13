import {
  describe,
  expect,
  it,
  vi,
  beforeEach,
  afterEach,
} from "vitest";
import { createRoot, createSignal } from "solid-js";
import type { JobState } from "~/lib/api-client.server";

const mockPollJob = vi.fn();
const mockPollJobSignals: Array<AbortSignal | undefined> = [];

vi.mock("@solidjs/router", () => ({
  revalidate: vi.fn(async () => undefined),
}));

class MockVibecheckApiError extends Error {
  public errorBody: unknown;
  public headers: Headers;
  constructor(
    message: string,
    public statusCode: number,
    errorBody: unknown = null,
    headers?: Headers | Record<string, string>,
  ) {
    super(message);
    this.name = "VibecheckApiError";
    this.errorBody = errorBody;
    this.headers = headers
      ? headers instanceof Headers
        ? headers
        : new Headers(headers)
      : new Headers();
  }
}

vi.mock("~/routes/analyze.data", () => ({
  getJobState: Object.assign((jobId: string, signal?: AbortSignal) => {
    mockPollJobSignals.push(signal);
    return mockPollJob(jobId);
  }, {
    keyFor: (jobId: string) => `vibecheck-job-state:${jobId}`,
  }),
  pollJobState: (jobId: string, signal?: AbortSignal) => {
    mockPollJobSignals.push(signal);
    return mockPollJob(jobId);
  },
}));

function makeJobState(overrides: Partial<JobState> = {}): JobState {
  return {
    job_id: "00000000-0000-0000-0000-000000000001",
    url: "https://news.example.com/a",
    status: "pending",
    attempt_id: "00000000-0000-0000-0000-0000000000aa",
    created_at: "2026-04-22T00:00:00Z",
    updated_at: "2026-04-22T00:00:00Z",
    cached: false,
    next_poll_ms: 1500,
    utterance_count: 0,
    ...overrides,
  } as JobState;
}

async function flushMicrotasks(rounds = 5): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await Promise.resolve();
  }
}

beforeEach(() => {
  mockPollJob.mockReset();
  mockPollJobSignals.length = 0;
  vi.useFakeTimers();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("createPollingResource", () => {
  it("fires the first poll immediately and surfaces state", async () => {
    const first = makeJobState({ status: "pending", next_poll_ms: 1500 });
    mockPollJob.mockResolvedValueOnce(first);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, error } = createPollingResource(() => "job-1");
      await flushMicrotasks();

      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(mockPollJob).toHaveBeenCalledWith("job-1");
      expect(state()).toEqual(first);
      expect(error()).toBeNull();
      dispose();
    });
  });

  it("schedules the next poll using next_poll_ms from the latest state", async () => {
    const first = makeJobState({ status: "pending", next_poll_ms: 500 });
    const second = makeJobState({ status: "analyzing", next_poll_ms: 500 });
    mockPollJob
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      createPollingResource(() => "job-cadence");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(499);
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      dispose();
    });
  });

  it("adapts cadence as next_poll_ms changes between ticks (500 -> 1500)", async () => {
    const first = makeJobState({ status: "pending", next_poll_ms: 500 });
    const second = makeJobState({ status: "analyzing", next_poll_ms: 1500 });
    const third = makeJobState({ status: "analyzing", next_poll_ms: 1500 });
    mockPollJob
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second)
      .mockResolvedValueOnce(third);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      createPollingResource(() => "job-adapt");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(1499);
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);

      dispose();
    });
  });

  it("clamps next_poll_ms below 500ms to 500ms and above 5000ms to 5000ms", async () => {
    const first = makeJobState({ status: "pending", next_poll_ms: 50 });
    const second = makeJobState({ status: "analyzing", next_poll_ms: 99999 });
    const third = makeJobState({ status: "analyzing", next_poll_ms: 1500 });
    mockPollJob
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second)
      .mockResolvedValueOnce(third);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      createPollingResource(() => "job-clamp");
      await flushMicrotasks();

      await vi.advanceTimersByTimeAsync(499);
      expect(mockPollJob).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(4999);
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);

      dispose();
    });
  });

  it("stops polling when status transitions to 'done'", async () => {
    const first = makeJobState({ status: "analyzing", next_poll_ms: 500 });
    const done = makeJobState({ status: "done", next_poll_ms: 500 });
    mockPollJob
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(done);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, error } = createPollingResource(() => "job-done");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(500);
      await flushMicrotasks();
      expect(state()?.status).toBe("done");
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      dispose();
    });
  });

  it("stops polling when status transitions to 'failed' and does not fire error()", async () => {
    const failed = makeJobState({ status: "failed", next_poll_ms: 500 });
    mockPollJob.mockResolvedValueOnce(failed);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, error } = createPollingResource(() => "job-failed");
      await flushMicrotasks();
      expect(state()?.status).toBe("failed");
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(error()).toBeNull();

      dispose();
    });
  });

  it("stops polling when status transitions to 'partial' and keeps the partial state", async () => {
    const partial = makeJobState({
      status: "partial" as JobState["status"],
      next_poll_ms: 500,
    });
    mockPollJob.mockResolvedValueOnce(partial);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, error } = createPollingResource(() => "job-partial");
      await flushMicrotasks();
      expect(state()?.status).toBe("partial");
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      dispose();
    });
  });

  it("sets error signal and stops after 3 consecutive fetch errors", async () => {
    mockPollJob
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500));

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error, state } = createPollingResource(() => "job-err");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);
      expect(error()).toBeInstanceOf(Error);
      expect(state()).toBeNull();

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);

      dispose();
    });
  });

  it("resets the failure counter after a transient 5xx followed by success", async () => {
    const ok = makeJobState({ status: "pending", next_poll_ms: 1500 });
    mockPollJob
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockResolvedValueOnce(ok)
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500));

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error, state } = createPollingResource(() => "job-reset");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);
      expect(error()).toBeNull();
      expect(state()).toEqual(ok);

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(4);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(5);
      expect(error()).toBeNull();

      dispose();
    });
  });

  it("treats 404 as terminal: sets error and stops without burning the 3-attempt budget", async () => {
    mockPollJob.mockRejectedValueOnce(
      new MockVibecheckApiError("missing", 404),
    );

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error } = createPollingResource(() => "job-404");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(error()).toBeInstanceOf(Error);

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      dispose();
    });
  });

  it("treats a Seroval-shaped 404 (plain Error with statusCode own-property) as terminal too", async () => {
    const serialized = new Error("missing");
    Object.assign(serialized, { statusCode: 404, name: "VibecheckApiError" });
    mockPollJob.mockRejectedValueOnce(serialized);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error } = createPollingResource(() => "job-404-shape");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(error()).toBeInstanceOf(Error);
      expect((error() as Error & { statusCode?: number }).statusCode).toBe(404);

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      dispose();
    });
  });

  it("fires no further fetches after createRoot is disposed", async () => {
    const first = makeJobState({ status: "pending", next_poll_ms: 500 });
    mockPollJob.mockResolvedValue(first);

    const { createPollingResource } = await import("./polling");

    const dispose = await new Promise<() => void>((resolve) => {
      createRoot(async (d) => {
        createPollingResource(() => "job-dispose");
        await flushMicrotasks();
        resolve(d);
      });
    });

    expect(mockPollJob).toHaveBeenCalledTimes(1);
    dispose();

    await vi.advanceTimersByTimeAsync(10_000);
    await flushMicrotasks();
    expect(mockPollJob).toHaveBeenCalledTimes(1);
  });

  it("resets state and restarts polling when jobId changes", async () => {
    const firstA = makeJobState({
      job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      status: "pending",
      next_poll_ms: 500,
    });
    const firstB = makeJobState({
      job_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      status: "pending",
      next_poll_ms: 500,
    });
    mockPollJob
      .mockResolvedValueOnce(firstA)
      .mockResolvedValueOnce(firstB);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const [id, setId] = createSignal("job-A");
      const { state } = createPollingResource(id);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenLastCalledWith("job-A");
      expect(state()?.job_id).toBe(firstA.job_id);

      setId("job-B");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenLastCalledWith("job-B");
      expect(state()?.job_id).toBe(firstB.job_id);

      dispose();
    });
  });

  it("clears state() and error() when jobId becomes empty", async () => {
    const first = makeJobState({ status: "pending", next_poll_ms: 500 });
    mockPollJob.mockResolvedValueOnce(first);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const [id, setId] = createSignal("job-X");
      const { state, error } = createPollingResource(id);
      await flushMicrotasks();
      expect(state()).not.toBeNull();
      expect(error()).toBeNull();

      setId("");
      await flushMicrotasks();
      expect(state()).toBeNull();
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      dispose();
    });
  });

  it("refetch() resumes polling after a terminal status and uses the fresh cadence", async () => {
    const done = makeJobState({ status: "done", next_poll_ms: 500 });
    const resumed = makeJobState({ status: "analyzing", next_poll_ms: 500 });
    mockPollJob
      .mockResolvedValueOnce(done)
      .mockResolvedValueOnce(resumed);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, refetch } = createPollingResource(() => "job-refetch");
      await flushMicrotasks();
      expect(state()?.status).toBe("done");
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(10_000);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      refetch();
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      expect(state()?.status).toBe("analyzing");

      dispose();
    });
  });

  it("refetch() preserves prior state() until the next poll resolves", async () => {
    const done = makeJobState({ status: "done", next_poll_ms: 500 });
    let resolveSecond!: (value: JobState) => void;
    const secondPromise = new Promise<JobState>((resolve) => {
      resolveSecond = resolve;
    });
    mockPollJob
      .mockResolvedValueOnce(done)
      .mockReturnValueOnce(secondPromise);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, refetch } = createPollingResource(
        () => "job-refetch-preserve",
      );
      await flushMicrotasks();
      expect(state()?.status).toBe("done");
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      refetch();
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      expect(state()?.status).toBe("done");

      const resumed = makeJobState({ status: "analyzing", next_poll_ms: 500 });
      resolveSecond(resumed);
      await flushMicrotasks();
      expect(state()?.status).toBe("analyzing");

      dispose();
    });
  });

  it("uses a terminal done seed without firing an immediate poll", async () => {
    const seed = makeJobState({
      job_id: "job-seeded-done",
      status: "done",
      next_poll_ms: 500,
    });

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, error } = createPollingResource(() => "job-seeded-done", {
        initialState: seed,
      });
      await flushMicrotasks();

      expect(state()).toEqual(seed);
      expect(error()).toBeNull();
      expect(mockPollJob).not.toHaveBeenCalled();
      dispose();
    });
  });

  it("uses a terminal partial seed without firing an immediate poll", async () => {
    const seed = makeJobState({
      job_id: "job-seeded-partial",
      status: "partial",
      next_poll_ms: 500,
    });

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state } = createPollingResource(() => "job-seeded-partial", {
        initialState: seed,
      });
      await flushMicrotasks();

      expect(state()).toEqual(seed);
      expect(mockPollJob).not.toHaveBeenCalled();
      dispose();
    });
  });

  it("schedules the first poll from a non-terminal seed cadence", async () => {
    const seed = makeJobState({
      job_id: "job-seeded-running",
      status: "analyzing",
      next_poll_ms: 500,
    });
    const next = makeJobState({ status: "done", next_poll_ms: 500 });
    mockPollJob.mockResolvedValueOnce(next);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state } = createPollingResource(() => "job-seeded-running", {
        initialState: seed,
      });
      await flushMicrotasks();

      expect(state()).toEqual(seed);
      expect(mockPollJob).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(499);
      expect(mockPollJob).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledWith("job-seeded-running");
      expect(state()).toEqual(next);
      dispose();
    });
  });

  it("refetch ignores a seed and forces a fresh poll", async () => {
    const seed = makeJobState({
      job_id: "job-seeded-refetch",
      status: "done",
      next_poll_ms: 500,
    });
    const refreshed = makeJobState({ status: "analyzing", next_poll_ms: 500 });
    mockPollJob.mockResolvedValueOnce(refreshed);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, refetch } = createPollingResource(
        () => "job-seeded-refetch",
        { initialState: seed },
      );
      await flushMicrotasks();
      expect(state()).toEqual(seed);
      expect(mockPollJob).not.toHaveBeenCalled();

      refetch();
      await flushMicrotasks();

      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(state()).toEqual(refreshed);
      dispose();
    });
  });

  it("does not reuse the initial seed after jobId changes to a different job", async () => {
    const seed = makeJobState({
      job_id: "job-seeded-a",
      status: "done",
      next_poll_ms: 500,
    });
    const next = makeJobState({
      job_id: "job-seeded-b",
      status: "done",
      next_poll_ms: 500,
    });
    mockPollJob.mockResolvedValueOnce(next);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const [id, setId] = createSignal("job-seeded-a");
      const { state } = createPollingResource(id, { initialState: seed });
      await flushMicrotasks();

      expect(state()).toEqual(seed);
      expect(mockPollJob).not.toHaveBeenCalled();

      setId("job-seeded-b");
      await flushMicrotasks();

      expect(mockPollJob).toHaveBeenCalledTimes(1);
      expect(mockPollJob).toHaveBeenCalledWith("job-seeded-b");
      expect(state()).toEqual(next);
      dispose();
    });
  });

  it("back-to-back pollJobState calls for the same jobId each trigger a fresh fetch (no cached query coalescing)", async () => {
    const { pollJobState } = await import("~/routes/analyze.data");
    const first = makeJobState({ status: "done", next_poll_ms: 500 });
    const second = makeJobState({ status: "analyzing", next_poll_ms: 500 });
    mockPollJob
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second);

    const [a, b] = await Promise.all([
      pollJobState("job-same"),
      pollJobState("job-same"),
    ]);

    expect(mockPollJob).toHaveBeenCalledTimes(2);
    expect(a).toEqual(first);
    expect(b).toEqual(second);
  });

  it("a deferred poll resolved after dispose does not mutate state or schedule another timer", async () => {
    let resolveFirst!: (value: JobState) => void;
    const firstPromise = new Promise<JobState>((resolve) => {
      resolveFirst = resolve;
    });
    mockPollJob.mockReturnValueOnce(firstPromise);

    const { createPollingResource } = await import("./polling");

    const handle = await new Promise<{
      dispose: () => void;
      state: () => JobState | null;
      error: () => Error | null;
    }>((resolve) => {
      createRoot((dispose) => {
        const { state, error } = createPollingResource(() => "job-defer-dispose");
        resolve({ dispose, state, error });
      });
    });

    await flushMicrotasks();
    expect(mockPollJob).toHaveBeenCalledTimes(1);

    handle.dispose();

    resolveFirst(makeJobState({ status: "analyzing", next_poll_ms: 500 }));
    await flushMicrotasks();

    expect(handle.state()).toBeNull();
    expect(handle.error()).toBeNull();

    await vi.advanceTimersByTimeAsync(10_000);
    await flushMicrotasks();
    expect(mockPollJob).toHaveBeenCalledTimes(1);
  });

  it("a deferred poll resolved after jobId changes does not mutate state for the new job", async () => {
    let resolveFirst!: (value: JobState) => void;
    const firstPromise = new Promise<JobState>((resolve) => {
      resolveFirst = resolve;
    });
    const secondState = makeJobState({
      job_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      status: "analyzing",
      next_poll_ms: 500,
    });
    mockPollJob
      .mockReturnValueOnce(firstPromise)
      .mockResolvedValueOnce(secondState);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const [id, setId] = createSignal("job-old");
      const { state } = createPollingResource(id);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      setId("job-new");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenLastCalledWith("job-new");
      expect(state()?.job_id).toBe(secondState.job_id);

      const stale = makeJobState({
        job_id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
        status: "done",
      });
      resolveFirst(stale);
      await flushMicrotasks();

      expect(state()?.job_id).toBe(secondState.job_id);
      dispose();
    });
  });

  it("refetch() after the 3-error terminal clears the error and resumes polling", async () => {
    const ok = makeJobState({ status: "pending", next_poll_ms: 1500 });
    mockPollJob
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockRejectedValueOnce(new MockVibecheckApiError("boom", 500))
      .mockResolvedValueOnce(ok);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { state, error, refetch } = createPollingResource(
        () => "job-refetch-err",
      );
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();

      expect(mockPollJob).toHaveBeenCalledTimes(3);
      expect(error()).toBeInstanceOf(Error);

      refetch();
      await flushMicrotasks();
      expect(error()).toBeNull();
      expect(state()).toEqual(ok);
      expect(mockPollJob).toHaveBeenCalledTimes(4);

      dispose();
    });
  });

  it("calls pollJobState with only serializable arguments on every tick", async () => {
    const ok = makeJobState({ status: "pending", next_poll_ms: 500 });
    mockPollJob.mockResolvedValue(ok);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      createPollingResource(() => "job-signal");
      await flushMicrotasks();
      expect(mockPollJobSignals).toHaveLength(1);
      expect(mockPollJobSignals[0]).toBeUndefined();

      await vi.advanceTimersByTimeAsync(500);
      await flushMicrotasks();
      expect(mockPollJobSignals).toHaveLength(2);
      expect(mockPollJobSignals[1]).toBeUndefined();

      dispose();
    });
  });

  it("handles 429 with Retry-After (seconds) by deferring next poll without burning the error budget", async () => {
    const ok = makeJobState({ status: "pending", next_poll_ms: 1500 });
    mockPollJob
      .mockResolvedValueOnce(ok)
      .mockRejectedValueOnce(
        new MockVibecheckApiError("rate limited", 429, null, {
          "Retry-After": "5",
        }),
      )
      .mockResolvedValueOnce(ok);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error } = createPollingResource(() => "job-429");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(4999);
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);
      expect(error()).toBeNull();

      dispose();
    });
  });

  it("survives three consecutive 429s without raising error() (429 must not consume the error budget)", async () => {
    const ok = makeJobState({ status: "pending", next_poll_ms: 1500 });
    mockPollJob
      .mockResolvedValueOnce(ok)
      .mockRejectedValueOnce(
        new MockVibecheckApiError("rl", 429, null, { "Retry-After": "1" }),
      )
      .mockRejectedValueOnce(
        new MockVibecheckApiError("rl", 429, null, { "Retry-After": "1" }),
      )
      .mockRejectedValueOnce(
        new MockVibecheckApiError("rl", 429, null, { "Retry-After": "1" }),
      )
      .mockResolvedValueOnce(ok);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error } = createPollingResource(() => "job-429-budget");
      await flushMicrotasks();
      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(4);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(5);
      expect(error()).toBeNull();

      dispose();
    });
  });

  it("falls back to clamped nextPollMs when 429 has no Retry-After header", async () => {
    const ok = makeJobState({ status: "pending", next_poll_ms: 1500 });
    mockPollJob
      .mockResolvedValueOnce(ok)
      .mockRejectedValueOnce(new MockVibecheckApiError("rl", 429))
      .mockResolvedValueOnce(ok);

    const { createPollingResource } = await import("./polling");

    await createRoot(async (dispose) => {
      const { error } = createPollingResource(() => "job-429-noheader");
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(1500);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(2);
      expect(error()).toBeNull();

      await vi.advanceTimersByTimeAsync(1499);
      expect(mockPollJob).toHaveBeenCalledTimes(2);

      await vi.advanceTimersByTimeAsync(1);
      await flushMicrotasks();
      expect(mockPollJob).toHaveBeenCalledTimes(3);
      expect(error()).toBeNull();

      dispose();
    });
  });
});

describe("parseRetryAfter", () => {
  it("parses integer seconds to milliseconds", async () => {
    const { parseRetryAfter } = await import("./polling");
    expect(parseRetryAfter("5")).toBe(5000);
    expect(parseRetryAfter("0")).toBe(0);
  });

  it("parses decimal seconds and rounds up", async () => {
    const { parseRetryAfter } = await import("./polling");
    expect(parseRetryAfter("1.25")).toBe(1250);
  });

  it("parses HTTP-date and returns ms until that instant", async () => {
    const { parseRetryAfter } = await import("./polling");
    const now = Date.parse("2026-04-22T00:00:00Z");
    const tenSecondsLater = "Wed, 22 Apr 2026 00:00:10 GMT";
    expect(parseRetryAfter(tenSecondsLater, now)).toBe(10_000);
  });

  it("returns 0 for a past HTTP-date", async () => {
    const { parseRetryAfter } = await import("./polling");
    const now = Date.parse("2026-04-22T00:01:00Z");
    expect(parseRetryAfter("Wed, 22 Apr 2026 00:00:00 GMT", now)).toBe(0);
  });

  it("returns null for null, empty, or unparseable input", async () => {
    const { parseRetryAfter } = await import("./polling");
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter("")).toBeNull();
    expect(parseRetryAfter("   ")).toBeNull();
    expect(parseRetryAfter("not a date or number")).toBeNull();
    expect(parseRetryAfter("-3")).toBeNull();
  });
});
