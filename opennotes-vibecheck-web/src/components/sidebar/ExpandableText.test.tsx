import { afterEach, describe, it, expect } from "vitest";
import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import ExpandableText from "./ExpandableText";

afterEach(() => {
  cleanup();
});

const SHORT = "Short utterance.";
const LONG =
  "This is a much longer utterance text that goes on for several phrases " +
  "and would otherwise blow up the sidebar layout if rendered inline. " +
  "It should be clamped to a few lines and reveal in a popover on click.";

describe("ExpandableText", () => {
  it("renders short text as a plain paragraph (no popover trigger)", () => {
    render(() => <ExpandableText text={SHORT} testId="x" />);
    const p = screen.getByTestId("x");
    expect(p.tagName.toLowerCase()).toBe("p");
    expect(screen.queryAllByRole("button").length).toBe(0);
    expect(p.textContent).toBe(SHORT);
  });

  it("renders long text behind a popover trigger with line-clamp", () => {
    render(() => <ExpandableText text={LONG} testId="x" />);
    const p = screen.getByTestId("x");
    expect(p.getAttribute("data-truncated")).toBe("true");
    const cls = p.getAttribute("class") ?? "";
    expect(cls).toMatch(/line-clamp-/);
    expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
  });

  it("opens a popover with the full text when the trigger is clicked", async () => {
    render(() => <ExpandableText text={LONG} testId="x" />);
    const trigger = screen.getByRole("button");
    await fireEvent.click(trigger);
    const expanded = await screen.findByTestId("expandable-text-content");
    expect(expanded.textContent).toContain(LONG);
  });

  it("treats text containing newlines as long even if char-count is small", () => {
    render(() => <ExpandableText text={"line one\nline two\nline three"} testId="x" />);
    expect(screen.getByTestId("x").getAttribute("data-truncated")).toBe("true");
    expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
  });
});
