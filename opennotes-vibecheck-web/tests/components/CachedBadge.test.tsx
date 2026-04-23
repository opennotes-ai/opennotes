import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import CachedBadge from "../../src/components/CachedBadge";

afterEach(() => {
  cleanup();
});

describe("<CachedBadge />", () => {
  it("renders nothing when cachedAt is null", () => {
    render(() => <CachedBadge cachedAt={null} />);
    expect(screen.queryByTestId("cached-badge")).toBeNull();
  });

  it("renders the badge with no timestamp when cachedAt is a recent ISO string", () => {
    // A cachedAt less than 1 minute old should render the badge but show no "Nm ago" marker.
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
