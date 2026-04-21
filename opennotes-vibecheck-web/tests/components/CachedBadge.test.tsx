import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import CachedBadge from "../../src/components/CachedBadge";

afterEach(() => {
  cleanup();
});

describe("<CachedBadge />", () => {
  it("renders the badge when cached=true", () => {
    render(() => <CachedBadge cached={true} />);
    const badge = screen.queryByTestId("cached-badge");
    expect(badge).not.toBeNull();
    expect(badge?.textContent?.toLowerCase()).toContain("cached");
  });

  it("renders nothing when cached=false", () => {
    render(() => <CachedBadge cached={false} />);
    expect(screen.queryByTestId("cached-badge")).toBeNull();
  });

  it("renders without a relative timestamp when cachedAt is missing", () => {
    render(() => <CachedBadge cached={true} cachedAt={null} />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).not.toMatch(/\d+\s*(m|h|d)\s*ago/i);
  });

  it("includes a relative timestamp when cachedAt is recent", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    render(() => <CachedBadge cached={true} cachedAt={twoHoursAgo} />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent).toMatch(/2h ago/);
  });

  it("ignores malformed cachedAt", () => {
    render(() => <CachedBadge cached={true} cachedAt="not-a-date" />);
    const badge = screen.getByTestId("cached-badge");
    expect(badge.textContent?.toLowerCase()).toContain("cached");
    expect(badge.textContent?.toLowerCase()).not.toMatch(/ago/);
  });
});
