import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import UtteranceRef from "./UtteranceRef";

afterEach(() => {
  cleanup();
});

describe("<UtteranceRef />", () => {
  it("renders the default turn label", () => {
    render(() => <UtteranceRef utteranceId="5" onClick={vi.fn()} />);

    expect(screen.getByRole("button", { name: "turn 5" })).toBeDefined();
  });

  it("renders a custom label", () => {
    render(() => (
      <UtteranceRef
        utteranceId="comment-7"
        label="around turn 7"
        onClick={vi.fn()}
      />
    ));

    expect(screen.getByRole("button", { name: "around turn 7" })).toBeDefined();
  });

  it("click invokes onClick with the utterance id", () => {
    const onClick = vi.fn();
    render(() => <UtteranceRef utteranceId="comment-7" onClick={onClick} />);

    fireEvent.click(screen.getByRole("button", { name: "turn comment-7" }));

    expect(onClick).toHaveBeenCalledWith("comment-7");
  });

  it("Enter invokes onClick with the utterance id", () => {
    const onClick = vi.fn();
    render(() => <UtteranceRef utteranceId="comment-8" onClick={onClick} />);

    fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });

    expect(onClick).toHaveBeenCalledWith("comment-8");
  });

  it("Space invokes onClick with the utterance id", () => {
    const onClick = vi.fn();
    render(() => <UtteranceRef utteranceId="comment-9" onClick={onClick} />);

    fireEvent.keyDown(screen.getByRole("button"), { key: " " });

    expect(onClick).toHaveBeenCalledWith("comment-9");
  });

  it("disabled renders muted non-interactive text", () => {
    const onClick = vi.fn();
    render(() => (
      <UtteranceRef utteranceId="comment-10" onClick={onClick} disabled />
    ));

    const ref = screen.getByText("turn comment-10");
    fireEvent.click(ref);

    expect(screen.queryByRole("button")).toBeNull();
    expect(ref.getAttribute("aria-disabled")).toBe("true");
    expect(onClick).not.toHaveBeenCalled();
  });

  it("applies the test id to the rendered element", () => {
    render(() => (
      <UtteranceRef
        utteranceId="comment-11"
        onClick={vi.fn()}
        testId="custom-utterance-ref"
      />
    ));

    expect(screen.getByTestId("custom-utterance-ref").textContent).toBe(
      "turn comment-11",
    );
  });
});
