// @vitest-environment node

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createViteServer } from "vitest/node";
import solid from "vite-plugin-solid";

const WEB_ROOT = fileURLToPath(new URL("../..", import.meta.url));

let server: Awaited<ReturnType<typeof createViteServer>>;

beforeAll(async () => {
  server = await createViteServer({
    root: WEB_ROOT,
    appType: "custom",
    logLevel: "silent",
    mode: "production",
    plugins: [
      {
        name: "analyze-data-stub",
        enforce: "pre",
        resolveId(id, importer) {
          if (id === "@solidjs/router") {
            return resolve(WEB_ROOT, "tests/ssr/router.stub.ts");
          }
          if (
            id === "./analyze.data" &&
            importer?.endsWith("/src/routes/analyze.tsx")
          ) {
            return resolve(WEB_ROOT, "tests/ssr/analyze-data.stub.ts");
          }
          if (id === "~/lib/notifications" || id.endsWith("/lib/notifications")) {
            return resolve(WEB_ROOT, "tests/ssr/notifications.stub.ts");
          }
          if (id === "~/lib/notify-preference" || id.endsWith("/lib/notify-preference")) {
            return resolve(WEB_ROOT, "tests/ssr/notify-preference.stub.ts");
          }
          return null;
        },
      },
      solid({ ssr: true }),
    ],
    resolve: {
      alias: [
        {
          find: "@solidjs/router",
          replacement: resolve(WEB_ROOT, "tests/ssr/router.stub.ts"),
        },
        {
          find: /^~\/routes\/analyze\.data$/,
          replacement: resolve(WEB_ROOT, "tests/ssr/analyze-data.stub.ts"),
        },
        {
          find: /^~\/lib\/notifications$/,
          replacement: resolve(WEB_ROOT, "tests/ssr/notifications.stub.ts"),
        },
        {
          find: /^~\/lib\/notify-preference$/,
          replacement: resolve(WEB_ROOT, "tests/ssr/notify-preference.stub.ts"),
        },
        { find: "~", replacement: resolve(WEB_ROOT, "src") },
      ],
    },
    server: { middlewareMode: true },
    ssr: { noExternal: true },
  });
}, 60_000);

afterAll(async () => {
  await server.close();
});

async function renderAnalyzePage(path: string): Promise<string> {
  const { createComponent, renderToString, ssr } =
    await server.ssrLoadModule("solid-js/web");
  const { MetaProvider } = await server.ssrLoadModule("@solidjs/meta");
  const router = await server.ssrLoadModule("@solidjs/router");
  const { default: AnalyzePage } =
    await server.ssrLoadModule("/src/routes/analyze.tsx");
  const { MemoryRouter, Route, createMemoryHistory } = router;
  const history = createMemoryHistory();
  history.set({ value: path, scroll: false, replace: true });

  return renderToString(() =>
    ssr(
      ["<html><head></head><body>", "</body></html>"],
      createComponent(MetaProvider, {
        get children() {
          return createComponent(MemoryRouter, {
            history,
            get children() {
              return createComponent(Route, {
                path: "/analyze",
                component: AnalyzePage,
              });
            },
          });
        },
      }),
    ),
  );
}

describe("AnalyzePage SSR — NotifyOnComplete safety", () => {
  it("SSR-renders /analyze without throwing when NotifyOnComplete is in the component tree", async () => {
    let html: string;
    let caughtError: unknown = null;
    try {
      html = await renderAnalyzePage("/analyze?job=ssr-notify-test");
    } catch (e) {
      caughtError = e;
      html = "";
    }
    expect(caughtError).toBeNull();
    expect(html.length).toBeGreaterThan(0);
  }, 15_000);

  it("SSR output does not contain window/Notification/localStorage access errors", async () => {
    const html = await renderAnalyzePage("/analyze?url=https%3A%2F%2Fnews.example.com%2Fstory");
    expect(html).toBeTruthy();
    expect(html).not.toContain("ReferenceError");
    expect(html).not.toContain("window is not defined");
    expect(html).not.toContain("localStorage is not defined");
    expect(html).not.toContain("Notification is not defined");
  }, 15_000);

  it("SSR-renders page shell with meta tags (nav is behind async gate, does not block SSR)", async () => {
    const html = await renderAnalyzePage("/analyze?job=ssr-nav-check");
    expect(html).toBeTruthy();
    expect(html).toContain("vibecheck");
    expect(html.length).toBeGreaterThan(0);
  }, 15_000);
});
