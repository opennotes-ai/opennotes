import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import type { components } from "../../lib/generated-types";
import UtteranceRef from "./UtteranceRef";
import { UtterancesProvider } from "./UtterancesContext";

type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

function anchor(utteranceId: string, position: number): UtteranceAnchor {
  return {
    utterance_id: utteranceId,
    position,
  };
}

afterEach(() => {
  cleanup();
});

describe("<UtteranceRef />", () => {
  it("renders the default label from utterance context", () => {
    render(() => (
      <UtterancesProvider
        value={[anchor("post-0-aaa", 1), anchor("comment-1-bbb", 2)]}
      >
        <UtteranceRef utteranceId="comment-1-bbb" onClick={vi.fn()} />
      </UtterancesProvider>
    ));

    expect(screen.getByRole("button", { name: "comment #1" })).toBeDefined();
  });

  it("renders a custom label verbatim", () => {
    render(() => (
      <UtteranceRef
        utteranceId="comment-7"
        label="source claim"
        onClick={vi.fn()}
      />
    ));

    expect(screen.getByRole("button", { name: "source claim" })).toBeDefined();
  });

  it("falls back without a provider", () => {
    render(() => (
      <UtteranceRef utteranceId="post-0-aaa" onClick={vi.fn()} />
    ));

    expect(screen.getByRole("button", { name: "item #?" })).toBeDefined();
  });

  it("click invokes onClick with the utterance id", () => {
    const onClick = vi.fn();
    render(() => (
      <UtterancesProvider value={[anchor("comment-7-aaa", 1)]}>
        <UtteranceRef utteranceId="comment-7-aaa" onClick={onClick} />
      </UtterancesProvider>
    ));

    fireEvent.click(screen.getByRole("button", { name: "comment #1" }));

    expect(onClick).toHaveBeenCalledWith("comment-7-aaa");
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
      <UtteranceRef utteranceId="comment-10-aaa" onClick={onClick} disabled />
    ));

    const ref = screen.getByText("item #?");
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
      "item #?",
    );
  });
});
