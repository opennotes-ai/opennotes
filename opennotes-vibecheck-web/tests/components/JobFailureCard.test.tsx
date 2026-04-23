import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@solidjs/testing-library";
import { MetaProvider } from "@solidjs/meta";
import { MemoryRouter, Route, createMemoryHistory } from "@solidjs/router";

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

import JobFailureCard from "../../src/components/JobFailureCard";
import type { ErrorCode } from "../../src/lib/api-client.server";

afterEach(() => {
  cleanup();
});

function renderCard(
  props: Parameters<typeof JobFailureCard>[0],
) {
  const history = createMemoryHistory();
  history.set({ value: "/analyze", scroll: false, replace: true });
  return render(() => (
    <MetaProvider>
      <MemoryRouter history={history}>
        <Route path="/analyze" component={() => <JobFailureCard {...props} />} />
      </MemoryRouter>
    </MetaProvider>
  ));
}

describe("<JobFailureCard />", () => {
  const URL = "https://example.com/article";

  it("renders as an alert region with the URL visible", async () => {
    renderCard({ url: URL, errorCode: "internal" });
    const card = await screen.findByRole("alert");
    expect(card).toBeDefined();
    expect(screen.getByTestId("job-failure-url").textContent).toBe(URL);
  });

  it("uses 'couldn't be parsed' copy for invalid_url", async () => {
    renderCard({ url: URL, errorCode: "invalid_url" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/couldn't be parsed/i);
  });

  it("uses host-specific copy for unsupported_site when errorHost is provided", async () => {
    renderCard({
      url: URL,
      errorCode: "unsupported_site",
      errorHost: "linkedin.com",
    });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/can't analyze linkedin\.com/i);
  });

  it("falls back to generic site copy for unsupported_site with no host", async () => {
    renderCard({ url: URL, errorCode: "unsupported_site" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/can't analyze that site/i);
  });

  it("uses 'couldn't reach' copy for upstream_error", async () => {
    renderCard({ url: URL, errorCode: "upstream_error" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/couldn't reach that page/i);
  });

  it("uses extraction-failed copy for extraction_failed", async () => {
    renderCard({ url: URL, errorCode: "extraction_failed" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/couldn't extract content/i);
  });

  it("uses timeout copy for timeout", async () => {
    renderCard({ url: URL, errorCode: "timeout" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/took too long/i);
  });

  it("uses rate-limit copy for rate_limited", async () => {
    renderCard({ url: URL, errorCode: "rate_limited" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/too many recent requests/i);
  });

  it("uses generic copy for internal and null", async () => {
    renderCard({ url: URL, errorCode: "internal" });
    let copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/something went wrong/i);
    cleanup();

    renderCard({ url: URL, errorCode: null as unknown as ErrorCode });
    copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toMatch(/something went wrong/i);
  });

  it("Try-again form posts 'url' to analyzeAction", async () => {
    renderCard({ url: URL, errorCode: "upstream_error" });
    const form = (await screen.findByTestId(
      "job-failure-try-again-form",
    )) as HTMLFormElement;
    expect(form.getAttribute("method")?.toLowerCase()).toBe("post");
    const hiddenUrl = form.querySelector(
      'input[name="url"]',
    ) as HTMLInputElement | null;
    expect(hiddenUrl).not.toBeNull();
    expect(hiddenUrl?.value).toBe(URL);
    const submitBtn = form.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement | null;
    expect(submitBtn?.textContent).toMatch(/try again/i);
  });

  it("invokes onTryAgain when the Try-again form is submitted", async () => {
    const onTryAgain = vi.fn();
    renderCard({ url: URL, errorCode: "internal", onTryAgain });
    const form = (await screen.findByTestId(
      "job-failure-try-again-form",
    )) as HTMLFormElement;
    fireEvent.submit(form);
    expect(onTryAgain).toHaveBeenCalledTimes(1);
  });

  it("renders a Back-to-home link pointing at /", async () => {
    renderCard({ url: URL, errorCode: "internal" });
    const home = await screen.findByTestId("job-failure-home");
    expect(home.getAttribute("href")).toBe("/");
  });
});
