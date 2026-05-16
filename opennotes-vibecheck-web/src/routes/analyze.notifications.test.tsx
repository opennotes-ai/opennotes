import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot, createSignal } from "solid-js";

vi.mock("~/lib/notifications", () => ({
  isSupported: vi.fn(() => true),
  notify: vi.fn(() => null),
  getPermission: vi.fn(() => "granted"),
  requestPermission: vi.fn(async () => "granted"),
}));

import { notify } from "~/lib/notifications";
import { titleFor, bodyFor, buildNotifyEffect } from "./analyze.notifications";

const notifyMock = notify as ReturnType<typeof vi.fn>;

beforeEach(() => {
  notifyMock.mockClear();
});

describe("titleFor", () => {
  it("returns success title for done", () => {
    expect(titleFor("done")).toBe("Vibecheck ready");
  });

  it("returns partial title for partial", () => {
    expect(titleFor("partial")).toBe("Vibecheck partially ready");
  });

  it("returns failure title for failed", () => {
    expect(titleFor("failed")).toBe("Vibecheck failed");
  });
});

describe("bodyFor", () => {
  it("returns success body for done", () => {
    expect(bodyFor("done")).toBe("Your analysis is complete.");
  });

  it("returns partial body for partial", () => {
    expect(bodyFor("partial")).toBe(
      "Some sections finished, others may be missing.",
    );
  });

  it("returns failure body for failed", () => {
    expect(bodyFor("failed")).toBe("We couldn't complete the analysis.");
  });
});

async function flush(): Promise<void> {
  await Promise.resolve();
}

describe("buildNotifyEffect (notify-on-complete guard logic)", () => {
  it("calls notify once when notifyEnabled=true and status transitions to done", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled, setNotifyEnabled] = createSignal(false);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => null,
      });

      setJobId("job-1");
      setNotifyEnabled(true);
      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);
      expect(notifyMock).toHaveBeenCalledWith("Vibecheck ready", {
        body: "Your analysis is complete.",
      });

      dispose();
    });
  });

  it("does not call notify a second time on re-render with same status and jobId", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled, setNotifyEnabled] = createSignal(false);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => null,
      });

      setJobId("job-2");
      setNotifyEnabled(true);
      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);

      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);

      dispose();
    });
  });

  it("fires a second notification for a new jobId after the first when new job starts non-terminal", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled, setNotifyEnabled] = createSignal(false);
      const initialStatuses: Record<string, string | null> = {};

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: (id) => initialStatuses[id] ?? null,
      });

      initialStatuses["job-3"] = "analyzing";
      setJobId("job-3");
      setNotifyEnabled(true);
      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);

      setJobStatus(null);
      initialStatuses["job-4"] = "analyzing";
      setJobId("job-4");
      setJobStatus("failed");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(2);

      dispose();
    });
  });

  it("does not call notify when notifyEnabled is false", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled] = createSignal(false);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => null,
      });

      setJobId("job-5");
      setJobStatus("done");
      await flush();

      expect(notifyMock).not.toHaveBeenCalled();

      dispose();
    });
  });

  it("calls notify with correct partial copy", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled, setNotifyEnabled] = createSignal(false);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => null,
      });

      setJobId("job-6");
      setNotifyEnabled(true);
      setJobStatus("partial");
      await flush();

      expect(notifyMock).toHaveBeenCalledWith("Vibecheck partially ready", {
        body: "Some sections finished, others may be missing.",
      });

      dispose();
    });
  });

  it("calls notify with correct failure copy", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled, setNotifyEnabled] = createSignal(false);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => null,
      });

      setJobId("job-7");
      setNotifyEnabled(true);
      setJobStatus("failed");
      await flush();

      expect(notifyMock).toHaveBeenCalledWith("Vibecheck failed", {
        body: "We couldn't complete the analysis.",
      });

      dispose();
    });
  });

  it("initial-terminal-done: initialStatusForJob returns 'done', live status 'done', notifyEnabled=true → notify NOT called", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled] = createSignal(true);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => "done",
      });

      setJobId("job-initial-done");
      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(0);

      dispose();
    });
  });

  it("initial-terminal-partial: initialStatusForJob returns 'partial', live status 'partial', notifyEnabled=true → notify NOT called", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled] = createSignal(true);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => "partial",
      });

      setJobId("job-initial-partial");
      setJobStatus("partial");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(0);

      dispose();
    });
  });

  it("initial-terminal-failed: initialStatusForJob returns 'failed', live status 'failed', notifyEnabled=true → notify NOT called", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled] = createSignal(true);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => "failed",
      });

      setJobId("job-initial-failed");
      setJobStatus("failed");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(0);

      dispose();
    });
  });

  it("in-progress→terminal: initialStatusForJob returns 'analyzing', live transitions to 'done', notifyEnabled=true → notify called once", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled] = createSignal(true);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => "analyzing",
      });

      setJobId("job-transition");
      setJobStatus("analyzing");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(0);

      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);
      expect(notifyMock).toHaveBeenCalledWith("Vibecheck ready", {
        body: "Your analysis is complete.",
      });

      dispose();
    });
  });

  it("late-enable: job already terminal when notifyEnabled flips true → notify does NOT fire (INVERTED)", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled, setNotifyEnabled] = createSignal(false);

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: () => "done",
      });

      setJobId("job-late");
      setJobStatus("done");
      await flush();

      expect(notifyMock).not.toHaveBeenCalled();

      setNotifyEnabled(true);
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(0);

      dispose();
    });
  });

  it("job-switch: new jobId whose initialStatusForJob returns terminal 'done' → notify does NOT fire (INVERTED)", async () => {
    await createRoot(async (dispose) => {
      const [jobStatus, setJobStatus] = createSignal<string | null>(null);
      const [jobId, setJobId] = createSignal<string | null>(null);
      const [notifyEnabled] = createSignal(true);
      const initialStatuses: Record<string, string | null> = {
        "job-switch-1": "analyzing",
        "job-switch-2": "done",
      };

      buildNotifyEffect({
        jobStatus,
        jobId,
        notifyEnabled,
        initialStatusForJob: (id) => initialStatuses[id] ?? null,
      });

      setJobId("job-switch-1");
      setJobStatus("done");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);

      setJobId("job-switch-2");
      await flush();

      expect(notifyMock).toHaveBeenCalledTimes(1);

      dispose();
    });
  });
});
