/// <reference types="@testing-library/jest-dom/vitest" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import { FeedbackPopover } from "./FeedbackPopover";

vi.mock("../../lib/feedback-client", () => ({
  openFeedback: vi.fn().mockResolvedValue({ id: "test-id" }),
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

afterEach(() => {
  cleanup();
});

describe("FeedbackPopover — focus-visible ring on icon buttons", () => {
  it("three popover icon buttons use focus-visible ring classes (not bare focus:ring)", () => {
    render(() => (
      <FeedbackPopover
        open={true}
        onOpenChange={() => {}}
        isDesktop={true}
        bellLocation="test"
      >
        <button type="button">trigger</button>
      </FeedbackPopover>
    ));

    const thumbsUp = screen.getByRole("button", { name: "Thumbs up" });
    const thumbsDown = screen.getByRole("button", { name: "Thumbs down" });
    const message = screen.getByRole("button", { name: "Send a message" });

    for (const btn of [thumbsUp, thumbsDown, message]) {
      // Intent: pointer-induced focus must not paint a ring; keyboard nav still does.
      // JSDOM can't compute :focus-visible heuristics — assert via class-token contract.
      expect(btn.className).toMatch(/focus-visible:ring-/);
      expect(btn.className).not.toMatch(/(?:^|\s)focus:ring-/);
    }
  });
});

describe("FeedbackPopover — icon button sizing", () => {
  it("three popover icon buttons render at h-8 w-8 (not h-10 w-10)", () => {
    render(() => (
      <FeedbackPopover
        open={true}
        onOpenChange={() => {}}
        isDesktop={true}
        bellLocation="test"
      >
        <button type="button">trigger</button>
      </FeedbackPopover>
    ));

    const thumbsUp = screen.getByRole("button", { name: "Thumbs up" });
    const thumbsDown = screen.getByRole("button", { name: "Thumbs down" });
    const message = screen.getByRole("button", { name: "Send a message" });

    for (const btn of [thumbsUp, thumbsDown, message]) {
      expect(btn.className).toContain("h-8");
      expect(btn.className).toContain("w-8");
      expect(btn.className).not.toContain("h-10");
      expect(btn.className).not.toContain("w-10");
    }
  });
});
