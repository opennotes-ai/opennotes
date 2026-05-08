/// <reference types="@testing-library/jest-dom/vitest" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@solidjs/testing-library";
import { FeedbackBell } from "./FeedbackBell";

vi.mock("../../lib/feedback-client", () => ({
  openFeedback: vi.fn().mockResolvedValue({ id: "test-feedback-id" }),
  submitFeedback: vi.fn().mockResolvedValue(undefined),
  submitFeedbackCombined: vi.fn().mockResolvedValue({ id: "combined-id" }),
  FeedbackApiError: class FeedbackApiError extends Error {
    constructor(
      public status: number,
      public body: unknown,
      message?: string,
    ) {
      super(message ?? `Feedback API error (${status})`);
      this.name = "FeedbackApiError";
    }
  },
}));

import { openFeedback, submitFeedback, submitFeedbackCombined } from "../../lib/feedback-client";

const mockOpenFeedback = vi.mocked(openFeedback);
const mockSubmitFeedback = vi.mocked(submitFeedback);
const mockSubmitFeedbackCombined = vi.mocked(submitFeedbackCombined);

function setupDesktopViewport() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: query === "(min-width: 768px)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function setupMobileViewport() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

beforeEach(() => {
  setupDesktopViewport();
  vi.clearAllMocks();
  mockOpenFeedback.mockResolvedValue({ id: "test-feedback-id" });
  mockSubmitFeedback.mockResolvedValue(undefined);
  mockSubmitFeedbackCombined.mockResolvedValue({ id: "combined-id" });
});

afterEach(() => {
  cleanup();
});

describe("FeedbackBell — aria-label", () => {
  it("includes bell_location in aria-label when ariaContext is not provided", () => {
    render(() => <FeedbackBell bell_location="card:safety-recommendation" />);

    const bell = screen.getByRole("button", {
      name: "Send feedback about card:safety-recommendation",
    });
    expect(bell).toBeInTheDocument();
  });

  it("uses ariaContext in aria-label when provided", () => {
    render(() => (
      <FeedbackBell
        bell_location="card:safety-recommendation"
        ariaContext="the safety recommendation card"
      />
    ));

    const bell = screen.getByRole("button", {
      name: "Send feedback about the safety recommendation card",
    });
    expect(bell).toBeInTheDocument();
  });
});

describe("FeedbackBell — popover opens on click (desktop)", () => {
  it("click opens the popover showing the three icon buttons", () => {
    render(() => <FeedbackBell bell_location="card:test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    expect(screen.getByRole("button", { name: "Thumbs up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thumbs down" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send a message" })).toBeInTheDocument();
  });
});

describe("FeedbackBell — popover opens on click (mobile)", () => {
  it("tap opens the popover on mobile viewport", () => {
    setupMobileViewport();
    render(() => <FeedbackBell bell_location="card:mobile-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    expect(screen.getByRole("button", { name: "Thumbs up" })).toBeInTheDocument();
  });
});

describe("FeedbackBell — Esc closes popover without opening surface", () => {
  it("pressing Esc closes popover and dialog does not appear", () => {
    render(() => <FeedbackBell bell_location="card:esc-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    expect(screen.getByRole("button", { name: "Thumbs up" })).toBeInTheDocument();

    fireEvent.keyDown(bell, { key: "Escape" });

    expect(screen.queryByRole("button", { name: "Thumbs up" })).not.toBeInTheDocument();
    expect(screen.queryByText("Send feedback")).not.toBeInTheDocument();
  });
});

describe("FeedbackBell — thumbs up opens desktop dialog with correct pre-selection", () => {
  it("click thumbs-up: popover closes, dialog renders, thumbs_up toggle is pressed, openFeedback called once with thumbs_up", async () => {
    render(() => <FeedbackBell bell_location="card:dialog-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    const thumbsUpBtn = screen.getByRole("button", { name: "Thumbs up" });
    fireEvent.click(thumbsUpBtn);

    const dialogTitle = await screen.findByText("Send feedback");
    expect(dialogTitle).toBeInTheDocument();

    const thumbsUpToggle = screen.getByRole("button", { name: "Thumbs up" });
    expect(thumbsUpToggle.getAttribute("aria-pressed")).toBe("true");

    await waitFor(() => {
      expect(mockOpenFeedback).toHaveBeenCalledTimes(1);
      expect(mockOpenFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          initial_type: "thumbs_up",
          bell_location: "card:dialog-test",
        }),
        expect.any(AbortSignal),
      );
    });
  });
});

describe("FeedbackBell — mobile drawer on thumbs down click", () => {
  it("click thumbs-down on mobile opens a drawer (data-slot=drawer-content) with thumbs_down pre-selected", async () => {
    setupMobileViewport();
    render(() => <FeedbackBell bell_location="card:drawer-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    const thumbsDownBtn = screen.getByRole("button", { name: "Thumbs down" });
    fireEvent.click(thumbsDownBtn);

    await screen.findByText("Send feedback");

    const thumbsDownToggle = screen.getByRole("button", { name: "Thumbs down" });
    expect(thumbsDownToggle.getAttribute("aria-pressed")).toBe("true");

    await waitFor(() => {
      expect(mockOpenFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          initial_type: "thumbs_down",
          bell_location: "card:drawer-test",
        }),
        expect.any(AbortSignal),
      );
    });
  });
});

describe("FeedbackBell — openFeedback failure: surface stays open, submit falls back to combined", () => {
  it("when openFeedback rejects, dialog still opens and onSend uses submitFeedbackCombined", async () => {
    mockOpenFeedback.mockRejectedValue(new Error("network error"));

    render(() => <FeedbackBell bell_location="card:fallback-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    fireEvent.click(screen.getByRole("button", { name: "Thumbs up" }));

    await screen.findByText("Send feedback");

    await waitFor(() => {
      expect(mockOpenFeedback).toHaveBeenCalledTimes(1);
    });

    const form = screen
      .getByPlaceholderText("name@example.com")
      .closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockSubmitFeedbackCombined).toHaveBeenCalledTimes(1);
      expect(mockSubmitFeedback).not.toHaveBeenCalled();
    });
  });
});

describe("FeedbackBell — surface closes after successful send", () => {
  it("after onSend resolves, the dialog is removed from the DOM", async () => {
    mockSubmitFeedback.mockResolvedValue(undefined);

    render(() => <FeedbackBell bell_location="card:close-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);

    fireEvent.click(screen.getByRole("button", { name: "Thumbs up" }));

    await screen.findByText("Send feedback");

    await waitFor(() => {
      expect(mockOpenFeedback).toHaveBeenCalledTimes(1);
    });

    const form = screen
      .getByPlaceholderText("name@example.com")
      .closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.queryByText("Send feedback")).not.toBeInTheDocument();
    });
  });
});

describe("FeedbackBell — feedbackId is reset between bell uses (Bug 1)", () => {
  it("after a successful submit, second use of the same bell does NOT PATCH the stale id", async () => {
    mockOpenFeedback.mockResolvedValueOnce({ id: "first-feedback-id" });
    mockSubmitFeedback.mockResolvedValue(undefined);

    render(() => <FeedbackBell bell_location="card:reuse-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);
    fireEvent.click(screen.getByRole("button", { name: "Thumbs up" }));

    await screen.findByText("Send feedback");

    await waitFor(() => {
      expect(mockOpenFeedback).toHaveBeenCalledTimes(1);
    });

    const form1 = screen
      .getByPlaceholderText("name@example.com")
      .closest("form") as HTMLFormElement;
    fireEvent.submit(form1);

    await waitFor(() => {
      expect(mockSubmitFeedback).toHaveBeenCalledWith(
        "first-feedback-id",
        expect.any(Object),
      );
      expect(screen.queryByText("Send feedback")).not.toBeInTheDocument();
    });

    mockSubmitFeedback.mockClear();
    mockSubmitFeedbackCombined.mockClear();

    let resolveSecondOpen: (value: { id: string }) => void = () => {};
    mockOpenFeedback.mockImplementationOnce(
      () =>
        new Promise<{ id: string }>((resolve) => {
          resolveSecondOpen = resolve;
        }),
    );

    fireEvent.click(bell);
    fireEvent.click(screen.getByRole("button", { name: "Thumbs up" }));

    await screen.findByText("Send feedback");

    const form2 = screen
      .getByPlaceholderText("name@example.com")
      .closest("form") as HTMLFormElement;
    fireEvent.submit(form2);

    await waitFor(() => {
      expect(
        mockSubmitFeedback.mock.calls.some(
          ([id]) => id === "first-feedback-id",
        ),
      ).toBe(false);
    });

    resolveSecondOpen({ id: "second-feedback-id" });
  });
});

describe("FeedbackBell — Send during in-flight open POST yields exactly one client call (Bug 2)", () => {
  it("clicking Send while open POST is still in flight results in exactly one feedback client call (no double-write)", async () => {
    let resolveOpen: (value: { id: string }) => void = () => {};
    mockOpenFeedback.mockImplementationOnce(
      () =>
        new Promise<{ id: string }>((resolve) => {
          resolveOpen = resolve;
        }),
    );
    mockSubmitFeedbackCombined.mockResolvedValue({ id: "combined-id" });
    mockSubmitFeedback.mockResolvedValue(undefined);

    render(() => <FeedbackBell bell_location="card:race-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });
    fireEvent.click(bell);
    fireEvent.click(screen.getByRole("button", { name: "Thumbs up" }));

    await screen.findByText("Send feedback");

    const form = screen
      .getByPlaceholderText("name@example.com")
      .closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    resolveOpen({ id: "race-feedback-id" });

    await waitFor(() => {
      expect(screen.queryByText("Send feedback")).not.toBeInTheDocument();
    });

    const totalCalls =
      mockSubmitFeedback.mock.calls.length +
      mockSubmitFeedbackCombined.mock.calls.length;
    expect(totalCalls).toBe(1);

    expect(mockSubmitFeedback).toHaveBeenCalledTimes(1);
    expect(mockSubmitFeedback).toHaveBeenCalledWith(
      "race-feedback-id",
      expect.objectContaining({
        final_type: "thumbs_up",
      }),
    );
    expect(mockSubmitFeedbackCombined).not.toHaveBeenCalled();
  });
});

describe("FeedbackBell — generation guard: re-open aborts previous in-flight POST (AC4)", () => {
  it("re-clicking bell then icon while first open POST is still in-flight: stale result does NOT update feedbackId", async () => {
    let resolveFirstOpen!: (value: { id: string }) => void;
    let firstSignal: AbortSignal | undefined;
    let callCount = 0;

    mockOpenFeedback.mockImplementation((_payload, signal?: AbortSignal) => {
      callCount++;
      if (callCount === 1) {
        firstSignal = signal;
        return new Promise<{ id: string }>((resolve) => {
          resolveFirstOpen = resolve;
        });
      }
      return Promise.resolve({ id: "second-open-id" });
    });

    render(() => <FeedbackBell bell_location="card:gen-test" />);

    const bell = screen.getByRole("button", { name: /Send feedback about/ });

    fireEvent.click(bell);
    fireEvent.click(screen.getByRole("button", { name: "Thumbs up" }));

    await screen.findByText("Send feedback");

    expect(firstSignal).toBeDefined();
    expect(firstSignal!.aborted).toBe(false);

    fireEvent.click(bell);
    const thumbsDownBtns = screen.getAllByRole("button", { name: "Thumbs down" });
    fireEvent.click(thumbsDownBtns[thumbsDownBtns.length - 1]);

    await waitFor(() => {
      expect(firstSignal!.aborted).toBe(true);
    });

    resolveFirstOpen({ id: "stale-open-id" });
    await Promise.resolve();

    await waitFor(() => {
      expect(mockOpenFeedback).toHaveBeenCalledTimes(2);
    });

    const form = screen
      .getByPlaceholderText("name@example.com")
      .closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockSubmitFeedback).toHaveBeenCalledTimes(1);
      expect(mockSubmitFeedback).toHaveBeenCalledWith(
        "second-open-id",
        expect.any(Object),
      );
    });

    expect(mockSubmitFeedback).not.toHaveBeenCalledWith(
      "stale-open-id",
      expect.any(Object),
    );
  });
});
