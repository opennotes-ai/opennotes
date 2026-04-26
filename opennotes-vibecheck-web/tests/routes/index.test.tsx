import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import { MetaProvider } from "@solidjs/meta";
import {
  MemoryRouter,
  Route,
  createMemoryHistory,
} from "@solidjs/router";

vi.mock("../../src/routes/analyze.data", () => {
  const mockFn = vi.fn();
  const stub = Object.assign(mockFn, {
    base: "/__mock_analyze_action",
    url: "/__mock_analyze_action",
    with: () => stub,
  });
  return {
    analyzeAction: stub,
  };
});

import HomePage from "../../src/routes/index";

afterEach(() => {
  cleanup();
});

function renderAt(path: string) {
  const history = createMemoryHistory();
  history.set({ value: path, scroll: false, replace: true });
  return render(() => (
    <MetaProvider>
      <MemoryRouter history={history}>
        <Route path="/" component={HomePage} />
      </MemoryRouter>
    </MetaProvider>
  ));
}

describe("HomePage (landing route)", () => {
  it("renders the headline and tagline", async () => {
    renderAt("/");
    expect(
      await screen.findByRole("heading", { name: /vibecheck/i }),
    ).toBeDefined();
    expect(
      await screen.findByText(/analyze any url for tone/i),
    ).toBeDefined();
  });

  it("renders the URL input and Analyze button", async () => {
    renderAt("/");
    expect(await screen.findByLabelText(/url to analyze/i)).toBeDefined();
    expect(
      await screen.findByRole("button", { name: /analyze/i }),
    ).toBeDefined();
  });

  it("surfaces invalid_url error from the query string", async () => {
    renderAt("/?error=invalid_url");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/couldn't be parsed/i);
  });

  it("surfaces upstream_error from the query string", async () => {
    renderAt("/?error=upstream_error");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/couldn't reach/i);
  });

  it("renders without an alert when no error query param is set", async () => {
    renderAt("/");
    await screen.findByRole("heading", { name: /vibecheck/i });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("surfaces host-specific copy for unsupported_site when host is in the query string", async () => {
    renderAt("/?error=unsupported_site&host=linkedin.com");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/can't analyze linkedin\.com/i);
  });

  it("surfaces generic unsupported_site copy when host is omitted", async () => {
    renderAt("/?error=unsupported_site");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/can't analyze that site/i);
  });

  it("ignores unknown error codes by showing the generic fallback", async () => {
    renderAt("/?error=mystery_code");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/something went wrong/i);
  });

  it("does not pin a specific duration in the latency hint", async () => {
    renderAt("/");
    await screen.findByRole("heading", { name: /vibecheck/i });
    const main = document.querySelector("main");
    expect(main).not.toBeNull();
    const text = main!.textContent ?? "";
    expect(text).toMatch(/recently analyzed/i);
    expect(text).toMatch(/longer/i);
    expect(text).not.toMatch(/\d+\s*[-–]\s*\d+\s*seconds?/i);
    expect(text).not.toMatch(/\d+\s*seconds?/i);
  });
});
