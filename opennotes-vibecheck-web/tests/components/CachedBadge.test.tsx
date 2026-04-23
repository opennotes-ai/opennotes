import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import CachedBadge from "../../src/components/CachedBadge";

afterEach(() => {
  cleanup();
});

describe("<CachedBadge />", () => {
  it("renders the badge without a timestamp when cachedAt is null", () => {
    render(() => <CachedBadge cachedAt={null} />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
    expect(badge.textContent?.toLowerCase()).not.toMatch(/ago/);
    expect(badge.textContent?.toLowerCase()).not.toMatch(/just now/);
  });

  it("renders the badge with a 'just now' marker when cachedAt is a recent ISO string", () => {
    const justNow = new Date(Date.now() - 5_000).toISOString();
    render(() => <CachedBadge cachedAt={justNow} />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
    expect(badge.textContent?.toLowerCase()).toMatch(/just now/);
  });

  it("includes a relative timestamp when cachedAt is a few hours ago", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    render(() => <CachedBadge cachedAt={twoHoursAgo} />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent).toMatch(/2h ago/);
  });

  it("renders the badge without a relative timestamp when cachedAt is malformed", () => {
    render(() => <CachedBadge cachedAt="not-a-date" />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
    expect(badge.textContent?.toLowerCase()).not.toMatch(/ago/);
  });
});
