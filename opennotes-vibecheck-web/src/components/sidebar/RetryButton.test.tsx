import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@solidjs/testing-library";

const { retrySectionActionMock, useActionMock } = vi.hoisted(() => ({
  retrySectionActionMock: vi.fn(),
  useActionMock: vi.fn(),
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
    useAction: () => {
      useActionMock();
      return retrySectionActionMock;
    },
  };
});

import RetryButton from "./RetryButton";

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  retrySectionActionMock.mockReset();
  useActionMock.mockReset();
});

describe("<RetryButton />", () => {
  it("is disabled while slotState is 'running'", () => {
    render(() => (
      <RetryButton
        jobId="job-1"
        slug="facts_claims__dedup"
        slotState="running"
      />
    ));
    const btn = screen.getByTestId(
      "retry-facts_claims__dedup",
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("is disabled while slotState is 'pending'", () => {
    render(() => (
      <RetryButton
        jobId="job-1"
        slug="facts_claims__dedup"
        slotState="pending"
      />
    ));
    const btn = screen.getByTestId(
      "retry-facts_claims__dedup",
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("is disabled while slotState is 'done' and does not invoke the retry action", () => {
    const onSuccess = vi.fn();
    render(() => (
      <RetryButton
        jobId="job-1"
        slug="facts_claims__dedup"
        slotState="done"
        onSuccess={onSuccess}
      />
    ));
    const btn = screen.getByTestId(
      "retry-facts_claims__dedup",
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(retrySectionActionMock).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("is enabled while slotState is 'failed'", () => {
    render(() => (
      <RetryButton
        jobId="job-1"
        slug="facts_claims__dedup"
        slotState="failed"
      />
    ));
    const btn = screen.getByTestId(
      "retry-facts_claims__dedup",
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("calls the retry action with form data and invokes onSuccess on happy path", async () => {
    retrySectionActionMock.mockResolvedValue({ ok: true });
    const onSuccess = vi.fn();
    render(() => (
      <RetryButton
        jobId="job-7"
        slug="tone_dynamics__scd"
        slotState="failed"
        onSuccess={onSuccess}
      />
    ));
    const btn = screen.getByTestId("retry-tone_dynamics__scd");
    fireEvent.click(btn);
    await waitFor(() => {
      expect(retrySectionActionMock).toHaveBeenCalledTimes(1);
    });
    const fd = retrySectionActionMock.mock.calls[0][0] as FormData;
    expect(fd.get("job_id")).toBe("job-7");
    expect(fd.get("slug")).toBe("tone_dynamics__scd");
    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });

  it("surfaces an inline error and does not call onSuccess when retry fails", async () => {
    retrySectionActionMock.mockRejectedValue(new Error("boom"));
    const onSuccess = vi.fn();
    render(() => (
      <RetryButton
        jobId="job-7"
        slug="tone_dynamics__scd"
        slotState="failed"
        onSuccess={onSuccess}
      />
    ));
    const btn = screen.getByTestId("retry-tone_dynamics__scd");
    fireEvent.click(btn);
    const errorMsg = await screen.findByTestId(
      "retry-error-tone_dynamics__scd",
    );
    expect(errorMsg.textContent).toMatch(/retry failed/i);
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
