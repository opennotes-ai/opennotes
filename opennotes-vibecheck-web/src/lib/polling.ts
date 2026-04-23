import {
  createEffect,
  createSignal,
  onCleanup,
  type Accessor,
} from "solid-js";
import type { JobState } from "~/lib/api-client.server";
import { pollJobState } from "~/routes/analyze.data";

export interface PollingResource {
  state: Accessor<JobState | null>;
  error: Accessor<Error | null>;
  refetch: () => void;
}

const MIN_INTERVAL_MS = 500;
const MAX_INTERVAL_MS = 5000;
const DEFAULT_INTERVAL_MS = 1500;
const MAX_CONSECUTIVE_ERRORS = 3;

function clampInterval(nextPollMs: number | null | undefined): number {
  if (typeof nextPollMs !== "number" || !Number.isFinite(nextPollMs)) {
    return DEFAULT_INTERVAL_MS;
  }
  return Math.min(MAX_INTERVAL_MS, Math.max(MIN_INTERVAL_MS, nextPollMs));
}

function isTerminalStatus(status: JobState["status"] | undefined): boolean {
  return status === "done" || status === "failed";
}

function is404Error(err: unknown): boolean {
  if (typeof err !== "object" || err === null) return false;
  const candidate = err as { statusCode?: unknown };
  return candidate.statusCode === 404;
}

function is429Error(err: unknown): boolean {
  if (typeof err !== "object" || err === null) return false;
  const candidate = err as { statusCode?: unknown };
  return candidate.statusCode === 429;
}

function readRetryAfterHeader(err: unknown): string | null {
  if (typeof err !== "object" || err === null) return null;
  const headers = (err as { headers?: unknown }).headers;
  if (!headers) return null;
  if (headers instanceof Headers) {
    return headers.get("Retry-After");
  }
  if (typeof headers === "object") {
    const record = headers as Record<string, string | undefined>;
    return (
      record["Retry-After"] ??
      record["retry-after"] ??
      null
    );
  }
  return null;
}

export function parseRetryAfter(
  raw: string | null,
  now: number = Date.now(),
): number | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  if (/^-/.test(trimmed)) return null;
  if (/^\d+(\.\d+)?$/.test(trimmed)) {
    const seconds = Number(trimmed);
    if (!Number.isFinite(seconds) || seconds < 0) return null;
    return Math.ceil(seconds * 1000);
  }
  const parsed = Date.parse(trimmed);
  if (!Number.isFinite(parsed)) return null;
  const delta = parsed - now;
  return delta > 0 ? delta : 0;
}

export function createPollingResource(
  jobId: Accessor<string>,
): PollingResource {
  const [state, setState] = createSignal<JobState | null>(null);
  const [error, setError] = createSignal<Error | null>(null);

  let timerId: ReturnType<typeof setTimeout> | null = null;
  let generation = 0;
  let consecutiveErrors = 0;
  let stopped = false;
  let currentJobId: string | null = null;

  const clearTimer = () => {
    if (timerId !== null) {
      clearTimeout(timerId);
      timerId = null;
    }
  };

  const tick = async (gen: number) => {
    if (gen !== generation || stopped || currentJobId === null) return;
    const idAtStart = currentJobId;
    try {
      const result = await pollJobState(idAtStart);
      if (gen !== generation || stopped) return;
      consecutiveErrors = 0;
      setError(null);
      setState(result);
      if (isTerminalStatus(result.status)) {
        stopped = true;
        clearTimer();
        return;
      }
      const interval = clampInterval(result.next_poll_ms);
      clearTimer();
      timerId = setTimeout(() => {
        timerId = null;
        void tick(gen);
      }, interval);
    } catch (err: unknown) {
      if (gen !== generation || stopped) return;
      const normalized =
        err instanceof Error ? err : new Error(String(err));
      if (is404Error(err)) {
        stopped = true;
        clearTimer();
        setError(normalized);
        return;
      }
      if (is429Error(err)) {
        const latest = state();
        const baseInterval = clampInterval(latest?.next_poll_ms);
        const retryAfterMs = parseRetryAfter(readRetryAfterHeader(err));
        const interval =
          retryAfterMs !== null
            ? Math.max(retryAfterMs, baseInterval)
            : baseInterval;
        clearTimer();
        timerId = setTimeout(() => {
          timerId = null;
          void tick(gen);
        }, interval);
        return;
      }
      consecutiveErrors += 1;
      console.error("createPollingResource: poll failed", normalized);
      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        stopped = true;
        clearTimer();
        setError(normalized);
        return;
      }
      const latest = state();
      const interval = clampInterval(latest?.next_poll_ms);
      clearTimer();
      timerId = setTimeout(() => {
        timerId = null;
        void tick(gen);
      }, interval);
    }
  };

  const start = (id: string) => {
    generation += 1;
    consecutiveErrors = 0;
    stopped = false;
    currentJobId = id;
    clearTimer();
    setError(null);
    setState(null);
    const gen = generation;
    void tick(gen);
  };

  createEffect(() => {
    const id = jobId();
    if (!id) {
      generation += 1;
      stopped = true;
      currentJobId = null;
      clearTimer();
      setState(null);
      setError(null);
      return;
    }
    start(id);
  });

  onCleanup(() => {
    generation += 1;
    stopped = true;
    currentJobId = null;
    clearTimer();
  });

  const refetch = () => {
    const id = jobId() || currentJobId;
    if (!id) return;
    generation += 1;
    consecutiveErrors = 0;
    stopped = false;
    currentJobId = id;
    clearTimer();
    setError(null);
    const gen = generation;
    void tick(gen);
  };

  return { state, error, refetch };
}
