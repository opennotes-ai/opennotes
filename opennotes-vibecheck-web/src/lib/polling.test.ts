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

class MockVibecheckApiError extends Error {
  public errorBody: unknown;
  constructor(
    message: string,
    public statusCode: number,
    errorBody: unknown = null,
  ) {
    super(message);
    this.name = "VibecheckApiError";
    this.errorBody = errorBody;
  }
}

vi.mock("~/routes/analyze.data", () => ({
  pollJobState: (jobId: string) => mockPollJob(jobId),
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
});
