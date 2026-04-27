import { test, expect } from "@playwright/test";
import { QUIZLET_REFERENCE_URL } from "./fixtures/quizlet";

/**
 * /embed/v1/start endpoint contract — covers AC#1, #2, #3, #5, #8 of TASK-1483.08.
 *
 * Cross-origin browser submission: served as a `data:` URL HTML form, the
 * browser POSTs to `/embed/v1/start` and follows the 303. This proves a
 * marketing page on a different origin can drop in the documented form
 * snippet and have it land on the live job page without CORS / preflight.
 */

test.describe("/embed/v1/start", () => {
  test("AC1+5+8a: cross-origin form POST lands on /analyze?job=...", async ({
    page,
    baseURL,
  }) => {
    test.setTimeout(60_000);
    const action = `${baseURL}/embed/v1/start`;
    const html = `<!doctype html><html><body>
      <form id="f" action="${action}" method="post">
        <input name="url" value="${QUIZLET_REFERENCE_URL}" />
        <button type="submit">Go</button>
      </form>
    </body></html>`;
    await page.goto(`data:text/html;base64,${Buffer.from(html).toString("base64")}`);
    await Promise.all([
      page.waitForURL((u) => u.pathname === "/analyze", { timeout: 30_000 }),
      page.locator("#f button").click(),
    ]);
    const parsed = new URL(page.url());
    expect(parsed.searchParams.get("job")).toBeTruthy();
  });

  test("AC4: invalid url falls back to /?error=invalid_url", async ({
    page,
    baseURL,
  }) => {
    const action = `${baseURL}/embed/v1/start`;
    const html = `<!doctype html><html><body>
      <form id="f" action="${action}" method="post">
        <input name="url" value="not-a-url" />
        <button type="submit">Go</button>
      </form>
    </body></html>`;
    await page.goto(`data:text/html;base64,${Buffer.from(html).toString("base64")}`);
    await Promise.all([
      page.waitForURL(
        (u) => u.pathname === "/" && u.searchParams.get("error") === "invalid_url",
        { timeout: 15_000 },
      ),
      page.locator("#f button").click(),
    ]);
  });

  test("AC3: GET returns 405 with Allow: POST", async ({ request, baseURL }) => {
    const response = await request.get(`${baseURL}/embed/v1/start`);
    expect(response.status()).toBe(405);
    expect(response.headers().allow).toBe("POST");
  });

  test("AC3: PUT/DELETE/OPTIONS each return 405 with Allow: POST", async ({
    request,
    baseURL,
  }) => {
    for (const method of ["PUT", "DELETE", "OPTIONS"] as const) {
      const response = await request.fetch(`${baseURL}/embed/v1/start`, {
        method,
      });
      expect(response.status(), `${method} should return 405`).toBe(405);
      expect(
        response.headers().allow,
        `${method} should advertise Allow: POST`,
      ).toBe("POST");
    }
  });

  // AC8d "exactly-once submit count" is exercised by the unit test in
  // src/routes/embed/v1/start.test.ts ("calls analyzeUrl exactly once per
  // POST"); the SolidStart server makes the downstream /api/analyze call
  // server-side, so it isn't observable from Playwright's page.route which
  // only intercepts browser-issued requests.
});
