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
        { find: "~", replacement: resolve(WEB_ROOT, "src") },
      ],
    },
    server: { middlewareMode: true },
    ssr: { noExternal: true },
  });

  await renderAnalyzeHead("/analyze");
}, 60_000);

afterAll(async () => {
  await server.close();
});

async function renderAnalyzeHead(path: string): Promise<string> {
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

describe("AnalyzePage SSR metadata", () => {
  it("renders social preview tags while a job route is loading", async () => {
    const head = await renderAnalyzeHead("/analyze?job=test-123");

    expect(head).toContain('property="og:title"');
    expect(head).toContain('property="og:description"');
    expect(head).toContain('property="og:url"');
    expect(head).toContain('property="og:image"');
    expect(head).toContain('name="twitter:image"');
    expect(head).toContain(
      "https://vibecheck.opennotes.ai/api/og?job=test-123",
    );
  }, 15_000);

  it("renders URL-derived fallback tags without a job id", async () => {
    const head = await renderAnalyzeHead(
      "/analyze?url=https%3A%2F%2Fnews.example.com%2Fstory",
    );

    expect(head).toContain('property="og:title"');
    expect(head).toContain('content="news.example.com — vibecheck"');
    expect(head).toContain('property="og:description"');
    expect(head).toContain('content="Vibecheck for: news.example.com"');
    expect(head).toContain('property="og:image"');
    expect(head).toContain('content="https://vibecheck.opennotes.ai/api/og"');
  });
});
