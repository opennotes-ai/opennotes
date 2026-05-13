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
    toString: () => "/__mock_analyze_action",
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

  it("uses exact 'That URL couldn't be parsed.' copy for invalid_url", async () => {
    renderCard({ url: URL, errorCode: "invalid_url" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("That URL couldn't be parsed.");
  });

  it("renders unsafe_url copy and Web Risk threat details", async () => {
    renderCard({
      url: "https://phishing.example.test/login",
      errorCode: "unsafe_url",
      webRiskFindings: [
        {
          url: "https://phishing.example.test/login",
          threat_types: ["MALWARE", "SOCIAL_ENGINEERING"],
        },
      ],
    });

    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe(
      "Web Risk flagged this URL before analysis.",
    );
    expect(screen.getByTestId("unsafe-url-finding").textContent).toContain(
      "https://phishing.example.test/login",
    );
    const threats = screen
      .getAllByTestId("unsafe-url-threat")
      .map((node) => node.textContent);
    expect(threats).toEqual(["malware", "social engineering"]);
  });

  it("uses exact host-specific copy for unsupported_site when errorHost is provided", async () => {
    renderCard({
      url: URL,
      errorCode: "unsupported_site",
      errorHost: "linkedin.com",
    });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("We can't analyze linkedin.com yet.");
  });

  it("uses exact generic site copy for unsupported_site with no host", async () => {
    renderCard({ url: URL, errorCode: "unsupported_site" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("We can't analyze that site yet.");
  });

  it("uses analyzer-availability copy for upstream_error (not page-content phrasing)", async () => {
    renderCard({ url: URL, errorCode: "upstream_error" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("The analyzer is temporarily unavailable.");
    // Regression for TASK-1483.16.08.18: limiter-backend outages route to
    // upstream_error and must NOT surface the extraction_failed
    // "page content" phrasing that misled extension users.
    expect(copy.textContent).not.toContain("page's content");
    expect(copy.textContent).not.toContain("couldn't read");
  });

  it("uses exact extraction_failed copy", async () => {
    renderCard({ url: URL, errorCode: "extraction_failed" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("We couldn't read this page's content.");
  });

  it("uses exact timeout copy", async () => {
    renderCard({ url: URL, errorCode: "timeout" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe(
      "The analysis took too long and was cancelled.",
    );
  });

  it("uses exact rate_limited copy", async () => {
    renderCard({ url: URL, errorCode: "rate_limited" });
    const copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe(
      "Too many recent requests. Try again in a moment.",
    );
  });

  it("uses exact generic copy for internal and null", async () => {
    renderCard({ url: URL, errorCode: "internal" });
    let copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("Something went wrong. Please try again.");
    cleanup();

    renderCard({ url: URL, errorCode: null as unknown as ErrorCode });
    copy = await screen.findByTestId("job-failure-copy");
    expect(copy.textContent).toBe("Something went wrong. Please try again.");
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

  it("Try-again form action resolves to the analyzeAction stub URL", async () => {
    renderCard({ url: URL, errorCode: "upstream_error" });
    const form = (await screen.findByTestId(
      "job-failure-try-again-form",
    )) as HTMLFormElement;
    const resolved =
      form.getAttribute("action") ??
      (typeof form.action === "string" ? form.action : "");
    expect(resolved).toContain("/__mock_analyze_action");
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

  // TASK-1488.19 — curated per-code detail line replaces raw error_message
  // rendering. Backend `error_message` (e.g. firecrawl_blocked / 403 /
  // /v2/scrape vendor envelopes) must never reach the customer-facing UI.

  describe("curated detail line", () => {
    const expected: Array<[ErrorCode | null, string]> = [
      [
        "invalid_url",
        "Check the URL is correctly formed and try again.",
      ],
      ["unsafe_url", "Web Risk flagged this URL as unsafe."],
      ["unsupported_site", "This site blocks automated readers."],
      [
        "upstream_error",
        "Our analyzer or one of its upstream providers is having trouble right now — try again in a moment.",
      ],
      [
        "extraction_failed",
        "This often happens when a site blocks automated readers (login walls, paywalls, captchas, or bot protection).",
      ],
      ["section_failure", "Some analysis sections couldn't complete."],
      [
        "timeout",
        "Try again in a moment — the analysis didn't finish in time.",
      ],
      ["rate_limited", "Too many recent requests. Try again shortly."],
      [
        "internal",
        "Something went wrong. Please try again or contact support.",
      ],
      [
        null,
        "Something went wrong. Please try again or contact support.",
      ],
    ];

    for (const [code, text] of expected) {
      it(`renders curated detail '${text}' for errorCode=${String(code)}`, async () => {
        renderCard({
          url: URL,
          errorCode: code as ErrorCode | null,
        });
        const detail = await screen.findByTestId("job-failure-detail");
        expect(detail.textContent).toBe(text);
      });
    }

    it("does not render any vendor-leak strings even when a leak candidate is forced via cast", async () => {
      // Anti-leak regression for TASK-1488.19. Codex review pointed out
      // a vacuous version of this test that asserted clean output for
      // clean inputs. Force a real leak candidate via cast so the
      // assertion is non-trivially testing prop suppression: if a
      // future refactor re-adds an `errorMessage` prop and renders it,
      // this test will fail.
      const leak =
        'tier 1: firecrawl_blocked: firecrawl /v2/scrape refused: 403 {"success":false,"error":"..."}';
      renderCard({
        url: URL,
        errorCode: "unsupported_site",
        errorHost: "linkedin.com",
        // Cast through unknown to slip an extra prop past the typed
        // surface. The component must not render this anywhere.
        ...({ errorMessage: leak } as unknown as Record<string, never>),
      });
      const card = await screen.findByTestId("job-failure-card");
      const text = card.textContent ?? "";
      expect(text).not.toContain("firecrawl");
      expect(text).not.toContain("/v2/");
      expect(text).not.toContain("403");
      expect(text).not.toContain("tier 1:");
      // Sanity: the component still renders the curated detail line.
      const detail = await screen.findByTestId("job-failure-detail");
      expect(detail.textContent).toBe(
        "This site blocks automated readers.",
      );
    });
  });
});
