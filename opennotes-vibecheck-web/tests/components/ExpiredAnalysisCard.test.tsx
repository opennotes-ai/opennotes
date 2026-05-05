import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import { MetaProvider } from "@solidjs/meta";
import { MemoryRouter, Route, createMemoryHistory } from "@solidjs/router";

vi.mock("../../src/routes/analyze.data", () => {
  const mockFn = vi.fn();
  const stub = Object.assign(mockFn, {
    base: "/__mock_analyze_action",
    url: "/__mock_analyze_action",
    with: () => stub,
    toString: () => "/__mock_analyze_action",
  });
  return {
    analyzeAction: stub,
  };
});

import ExpiredAnalysisCard from "../../src/components/ExpiredAnalysisCard";

afterEach(() => {
  cleanup();
});

function renderCard(props: Parameters<typeof ExpiredAnalysisCard>[0]) {
  const history = createMemoryHistory();
  history.set({ value: "/analyze", scroll: false, replace: true });
  return render(() => (
    <MetaProvider>
      <MemoryRouter history={history}>
        <Route path="/analyze" component={() => <ExpiredAnalysisCard {...props} />} />
      </MemoryRouter>
    </MetaProvider>
  ));
}

describe("<ExpiredAnalysisCard />", () => {
  const URL = "https://example.com/article";

  it("renders as an alert region with the URL visible", async () => {
    renderCard({ url: URL });
    const card = await screen.findByRole("alert");
    expect(card).toBeDefined();
    expect(card.getAttribute("data-testid")).toBe("expired-analysis-card");
    expect(screen.getByTestId("expired-analysis-url").textContent).toContain(URL);
  });

  it('renders title "This analysis has expired"', async () => {
    renderCard({ url: URL });
    const title = await screen.findByTestId("expired-analysis-title");
    expect(title.textContent).toBe("This analysis has expired");
  });

  it("renders Re-analyze form with correct url when url prop is provided", async () => {
    renderCard({ url: URL });
    const form = (await screen.findByTestId("expired-analysis-form")) as HTMLFormElement;
    expect(form.getAttribute("method")?.toLowerCase()).toBe("post");
    const hiddenUrl = form.querySelector('input[name="url"]') as HTMLInputElement | null;
    expect(hiddenUrl).not.toBeNull();
    expect(hiddenUrl?.value).toBe(URL);
  });

  it("Re-analyze button has aria-label mentioning the host", async () => {
    renderCard({ url: URL });
    const btn = (await screen.findByTestId("expired-analysis-reanalyze")) as HTMLButtonElement;
    const ariaLabel = btn.getAttribute("aria-label") ?? "";
    expect(ariaLabel).toContain("example.com");
  });

  it("hides Re-analyze button and shows home link when url is null", async () => {
    renderCard({ url: null });
    const form = screen.queryByTestId("expired-analysis-form");
    expect(form).toBeNull();
    const home = await screen.findByTestId("expired-analysis-home");
    expect(home.getAttribute("href")).toBe("/");
  });

  it("Re-analyze form action resolves to analyzeAction stub", async () => {
    renderCard({ url: URL });
    const form = (await screen.findByTestId("expired-analysis-form")) as HTMLFormElement;
    const resolved =
      form.getAttribute("action") ??
      (typeof form.action === "string" ? form.action : "");
    expect(resolved).toContain("/__mock_analyze_action");
  });

  it("renders formatted expiredAt date when provided", async () => {
    renderCard({ url: URL, expiredAt: new Date("2026-04-28T10:00:00Z") });
    const dateEl = await screen.findByTestId("expired-analysis-date");
    expect(dateEl).not.toBeNull();
    const text = dateEl.textContent ?? "";
    expect(text.match(/Apr|28|2026/)).not.toBeNull();
  });

  it("does not render expiredAt date when null", async () => {
    renderCard({ url: URL, expiredAt: null });
    expect(screen.queryByTestId("expired-analysis-date")).toBeNull();
  });
});
