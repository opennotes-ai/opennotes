import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearHighlight,
  ensureHighlightStyles,
  scrollToUtterance,
  type ScrollState,
} from "./utterance-scroll";

function iframeWithHtml(html: string): HTMLIFrameElement {
  const iframe = document.createElement("iframe");
  const iframeDoc = document.implementation.createHTMLDocument("Archive");
  iframeDoc.body.innerHTML = html;
  Object.defineProperty(iframe, "contentDocument", {
    configurable: true,
    value: iframeDoc,
  });
  return iframe;
}

describe("utterance-scroll helpers", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, "debug").mockImplementation(() => undefined);
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 1;
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("scrolls the matching utterance and applies flash then ring markers", () => {
    const iframe = iframeWithHtml('<p data-utterance-id="comment-1">Target</p>');
    const state: ScrollState = { lastHighlightedId: null };

    const scrolled = scrollToUtterance(iframe, "comment-1", state);

    const target = iframe.contentDocument?.querySelector("[data-utterance-id]");
    expect(scrolled).toBe(true);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
    expect(target?.hasAttribute("data-vibecheck-flash")).toBe(true);
    expect(target?.hasAttribute("data-vibecheck-ring")).toBe(true);

    vi.advanceTimersByTime(1100);

    expect(target?.hasAttribute("data-vibecheck-flash")).toBe(false);
    expect(target?.hasAttribute("data-vibecheck-ring")).toBe(true);
  });

  it("returns false without mutation when the utterance is missing", () => {
    const iframe = iframeWithHtml('<p data-utterance-id="comment-1">Target</p>');
    const state: ScrollState = { lastHighlightedId: null };

    const scrolled = scrollToUtterance(iframe, "comment-404", state);

    expect(scrolled).toBe(false);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(
      iframe.contentDocument?.querySelector("[data-vibecheck-ring]"),
    ).toBeNull();
  });

  it("returns false when no iframe is available", () => {
    const state: ScrollState = { lastHighlightedId: null };

    expect(scrollToUtterance(undefined, "comment-1", state)).toBe(false);
  });

  it("returns false when the iframe document is not loaded", () => {
    const iframe = document.createElement("iframe");
    Object.defineProperty(iframe, "contentDocument", {
      configurable: true,
      value: null,
    });
    const state: ScrollState = { lastHighlightedId: null };

    expect(scrollToUtterance(iframe, "comment-1", state)).toBe(false);
  });

  it("keeps only the most recently selected utterance ringed", () => {
    const iframe = iframeWithHtml(
      '<p data-utterance-id="comment-1">First</p><p data-utterance-id="comment-2">Second</p>',
    );
    const state: ScrollState = { lastHighlightedId: null };

    scrollToUtterance(iframe, "comment-1", state);
    scrollToUtterance(iframe, "comment-2", state);

    const first = iframe.contentDocument?.querySelector(
      '[data-utterance-id="comment-1"]',
    );
    const second = iframe.contentDocument?.querySelector(
      '[data-utterance-id="comment-2"]',
    );
    expect(first?.hasAttribute("data-vibecheck-ring")).toBe(false);
    expect(second?.hasAttribute("data-vibecheck-ring")).toBe(true);
  });

  it("injects highlight styles only once", () => {
    const iframe = iframeWithHtml("<p>Target</p>");
    const iframeDoc = iframe.contentDocument;
    if (!iframeDoc) throw new Error("test iframe missing contentDocument");

    ensureHighlightStyles(iframeDoc);
    ensureHighlightStyles(iframeDoc);

    expect(
      iframeDoc.head.querySelectorAll("style[data-vibecheck-utterance-style]"),
    ).toHaveLength(1);
  });

  it("clearHighlight removes the current ring", () => {
    const iframe = iframeWithHtml('<p data-utterance-id="comment-1">Target</p>');
    const state: ScrollState = { lastHighlightedId: null };
    scrollToUtterance(iframe, "comment-1", state);

    clearHighlight(iframe, state);

    expect(
      iframe.contentDocument
        ?.querySelector('[data-utterance-id="comment-1"]')
        ?.hasAttribute("data-vibecheck-ring"),
    ).toBe(false);
    expect(state.lastHighlightedId).toBeNull();
  });
});
