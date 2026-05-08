import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@solidjs/testing-library";
import { FeedbackForm } from "./FeedbackForm";

afterEach(() => {
  cleanup();
});

describe("<FeedbackForm />", () => {
  it("thumbs_up initial: toggle pressed, Send enabled even with empty message", () => {
    render(() => (
      <FeedbackForm initialType="thumbs_up" onSend={vi.fn()} />
    ));

    const thumbsUp = screen.getByRole("button", { name: "Thumbs up" });
    expect(thumbsUp.getAttribute("aria-pressed")).toBe("true");

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("message initial + empty message: Send is disabled", () => {
    render(() => (
      <FeedbackForm initialType="message" onSend={vi.fn()} />
    ));

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("message initial + 4 chars: Send is still disabled (gate is <=4)", () => {
    render(() => (
      <FeedbackForm initialType="message" onSend={vi.fn()} />
    ));

    const textarea = screen.getByPlaceholderText("Message…");
    fireEvent.input(textarea, { target: { value: "abcd" } });

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("message initial + 5 chars: Send becomes enabled", () => {
    render(() => (
      <FeedbackForm initialType="message" onSend={vi.fn()} />
    ));

    const textarea = screen.getByPlaceholderText("Message…");
    fireEvent.input(textarea, { target: { value: "abcde" } });

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("message initial → switch to thumbs_up: Send enabled regardless of message", () => {
    render(() => (
      <FeedbackForm initialType="message" onSend={vi.fn()} />
    ));

    const thumbsUpToggle = screen.getByRole("button", { name: "Thumbs up" });
    fireEvent.click(thumbsUpToggle);

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("Send calls onSend with email, message, and final_type", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);

    render(() => (
      <FeedbackForm initialType="thumbs_up" onSend={onSend} />
    ));

    const emailInput = screen.getByPlaceholderText("name@example.com");
    fireEvent.input(emailInput, { target: { value: "x@y.com" } });

    const textarea = screen.getByPlaceholderText("Message…");
    fireEvent.input(textarea, { target: { value: "hi" } });

    const form = emailInput.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend).toHaveBeenCalledWith({
        email: "x@y.com",
        message: "hi",
        final_type: "thumbs_up",
      });
    });
  });

  it("change-of-mind: initialType=thumbs_up but user toggles to thumbs_down, onSend payload reflects final_type=thumbs_down (not initial)", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);

    render(() => (
      <FeedbackForm initialType="thumbs_up" onSend={onSend} />
    ));

    const thumbsUpToggle = screen.getByRole("button", { name: "Thumbs up" });
    expect(thumbsUpToggle.getAttribute("aria-pressed")).toBe("true");

    const thumbsDownToggle = screen.getByRole("button", {
      name: "Thumbs down",
    });
    fireEvent.click(thumbsDownToggle);

    expect(thumbsDownToggle.getAttribute("aria-pressed")).toBe("true");
    expect(thumbsUpToggle.getAttribute("aria-pressed")).toBe("false");

    const emailInput = screen.getByPlaceholderText("name@example.com");
    fireEvent.input(emailInput, { target: { value: "u@e.com" } });

    const form = emailInput.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledTimes(1);
    });

    const payload = onSend.mock.calls[0]?.[0] as {
      email: string | null;
      message: string | null;
      final_type: string;
    };
    expect(payload.final_type).toBe("thumbs_down");
    expect(payload.final_type).not.toBe("thumbs_up");
    expect(payload.email).toBe("u@e.com");
  });

  it("change-of-mind: initialType=thumbs_down → toggle to message + 5+ chars, payload final_type=message", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);

    render(() => (
      <FeedbackForm initialType="thumbs_down" onSend={onSend} />
    ));

    const messageToggle = screen.getByRole("button", {
      name: "Send a message",
    });
    fireEvent.click(messageToggle);

    expect(messageToggle.getAttribute("aria-pressed")).toBe("true");

    const textarea = screen.getByPlaceholderText("Message…");
    fireEvent.input(textarea, { target: { value: "longer message" } });

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);

    const form = textarea.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(onSend).toHaveBeenCalledTimes(1);
    });

    const payload = onSend.mock.calls[0]?.[0] as {
      message: string | null;
      final_type: string;
    };
    expect(payload.final_type).toBe("message");
    expect(payload.final_type).not.toBe("thumbs_down");
    expect(payload.message).toBe("longer message");
  });

  it("onSend rejects → inline error appears, fields preserved, Send re-enabled", async () => {
    const onSend = vi.fn().mockRejectedValue(new Error("network"));

    render(() => (
      <FeedbackForm initialType="thumbs_up" onSend={onSend} />
    ));

    const emailInput = screen.getByPlaceholderText(
      "name@example.com",
    ) as HTMLInputElement;
    fireEvent.input(emailInput, { target: { value: "fail@example.com" } });

    const textarea = screen.getByPlaceholderText(
      "Message…",
    ) as HTMLTextAreaElement;
    fireEvent.input(textarea, { target: { value: "some message" } });

    const form = emailInput.closest("form") as HTMLFormElement;
    fireEvent.submit(form);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn't send");

    expect(emailInput.value).toBe("fail@example.com");
    expect(textarea.value).toBe("some message");

    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
  });
});
