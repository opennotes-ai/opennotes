import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const EXTENSION_DIR = new URL("../", import.meta.url);
const FIXTURES_DIR = new URL("fixtures/", import.meta.url);

async function readExtensionFile(filePath) {
  return readFile(new URL(filePath, EXTENSION_DIR), "utf8");
}

async function readFixture(name) {
  return readFile(new URL(`${name}.html`, FIXTURES_DIR), "utf8");
}

function loadHappyDom() {
  const worktreeRoot = path.resolve(__dirname, "../..");
  const worktreeRequire = createRequire(path.join(worktreeRoot, "_resolve-anchor.js"));
  return worktreeRequire("happy-dom");
}

async function createDomContext({ url, fixtureHtml }) {
  const { Window } = loadHappyDom();
  const win = new Window({ url });
  win.document.write(fixtureHtml);

  return win;
}

function makeClickAllMatchingSpy(win) {
  const matched = [];

  const spy = async (rawSpecs) => {
    const specs = Array.isArray(rawSpecs) ? rawSpecs : [rawSpecs];
    for (const spec of specs) {
      const selector = typeof spec === "string" ? spec : spec.selector;
      try {
        const elements = Array.from(win.document.querySelectorAll(selector));
        for (const el of elements) {
          matched.push({ selector, text: el.textContent?.trim() || "" });
        }
      } catch {
      }
    }
    return { clicks: matched.length, useful_clicks: matched.length, scrolls: 0, iterations: 1, timed_out: false };
  };

  spy.matched = matched;
  return spy;
}

function makeScrollSpy() {
  return async () => ({ scrolls: 1, timed_out: false });
}

function makeWaitForSelectorSpy(win) {
  return async (selector) => {
    try {
      return win.document.querySelector(selector) || null;
    } catch {
      return null;
    }
  };
}

function makeSleepSpy() {
  return async () => {};
}

async function loadStrategyInContext(win, strategyFile) {
  const source = await readExtensionFile(strategyFile);

  const context = {
    globalThis: {},
    console,
    location: win.location,
    document: win.document,
    window: win,
    URL: win.URL,
    setTimeout: win.setTimeout.bind(win),
    clearTimeout: win.clearTimeout.bind(win),
    performance: win.performance,
    MutationObserver: win.MutationObserver,
  };
  context.globalThis = context;
  context.window = context;

  vm.runInContext(source, vm.createContext(context), { filename: strategyFile });

  return context.__vibecheckExpand_strategies || {};
}

test("reddit strategy: registers correct host keys", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.reddit.com/r/test/comments/abc/title/" });
  win.document.write(await readFixture("reddit"));

  const strategies = await loadStrategyInContext(win, "content/sites/reddit.js");

  assert.ok("reddit.com" in strategies, "reddit.com key expected");
  assert.ok("old.reddit.com" in strategies, "old.reddit.com key expected");
});

test("reddit strategy: does not throw against new-Reddit fixture and finds clickable elements", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.reddit.com/r/test/comments/abc/title/" });
  win.document.write(await readFixture("reddit"));

  const strategies = await loadStrategyInContext(win, "content/sites/reddit.js");

  const clickSpy = makeClickAllMatchingSpy(win);
  const result = await strategies["reddit.com"]({ clickAllMatching: clickSpy });

  assert.ok(typeof result === "object" && result !== null, "strategy must return an object");
  assert.ok(typeof result.clicks === "number", "result.clicks must be a number");
  assert.ok(typeof result.scrolls === "number", "result.scrolls must be a number");
  assert.ok(clickSpy.matched.length > 0, "at least one element should match reddit selectors in fixture");
});

test("reddit strategy: does not throw against old-Reddit fixture and finds morechildren elements", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://old.reddit.com/r/test/comments/abc/title/" });
  win.document.write(await readFixture("reddit-old"));

  const strategies = await loadStrategyInContext(win, "content/sites/reddit.js");

  const clickSpy = makeClickAllMatchingSpy(win);
  const result = await strategies["old.reddit.com"]({ clickAllMatching: clickSpy });

  assert.ok(typeof result === "object" && result !== null, "strategy must return an object");
  assert.ok(clickSpy.matched.length > 0, "at least one .morechildren a element should match in old-Reddit fixture");
  const hasMokechildren = clickSpy.matched.some((m) => m.selector === ".morechildren a");
  assert.ok(hasMokechildren, ".morechildren a selector should find elements in old-Reddit fixture");
});

test("youtube strategy: registers correct host key", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" });
  win.document.write(await readFixture("youtube"));

  const strategies = await loadStrategyInContext(win, "content/sites/youtube.js");

  assert.ok("youtube.com" in strategies, "youtube.com key expected");
});

test("youtube strategy: does not throw against fixture with ytd-comments present", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" });
  win.document.write(await readFixture("youtube"));

  const strategies = await loadStrategyInContext(win, "content/sites/youtube.js");

  const clickSpy = makeClickAllMatchingSpy(win);
  const scrollSpy = makeScrollSpy();
  const waitSpy = makeWaitForSelectorSpy(win);

  const result = await strategies["youtube.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
    waitForSelector: waitSpy,
  });

  assert.ok(typeof result === "object" && result !== null, "strategy must return an object");
  assert.ok(typeof result.clicks === "number", "result.clicks must be a number");
  assert.ok(typeof result.scrolls === "number", "result.scrolls must be a number");
});

test("youtube strategy: fixture contains at least one known youtube selector element", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" });
  win.document.write(await readFixture("youtube"));

  const clickSpy = makeClickAllMatchingSpy(win);
  const scrollSpy = makeScrollSpy();
  const waitSpy = makeWaitForSelectorSpy(win);

  const strategies = await loadStrategyInContext(win, "content/sites/youtube.js");

  await strategies["youtube.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
    waitForSelector: waitSpy,
  });

  const knownSelectors = [
    "ytd-comment-replies-renderer #more-replies button",
    "ytd-continuation-item-renderer button",
    "tp-yt-paper-button#more",
    "ytd-button-renderer#more-replies button",
  ];
  const foundAny = knownSelectors.some((sel) => clickSpy.matched.some((m) => m.selector === sel));
  assert.ok(foundAny, `at least one known youtube selector should find elements in fixture; matched: ${JSON.stringify(clickSpy.matched.map((m) => m.selector))}`);
});

test("tiktok strategy: registers correct host key", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.tiktok.com/@user/video/123456789" });
  win.document.write(await readFixture("tiktok"));

  const strategies = await loadStrategyInContext(win, "content/sites/tiktok.js");

  assert.ok("tiktok.com" in strategies, "tiktok.com key expected");
});

test("tiktok strategy: does not throw when comment list is present in fixture", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.tiktok.com/@user/video/123456789" });
  win.document.write(await readFixture("tiktok"));

  const strategies = await loadStrategyInContext(win, "content/sites/tiktok.js");

  const clickSpy = makeClickAllMatchingSpy(win);
  const scrollSpy = makeScrollSpy();
  const waitSpy = makeWaitForSelectorSpy(win);
  const sleepSpy = makeSleepSpy();

  const result = await strategies["tiktok.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
    waitForSelector: waitSpy,
    sleep: sleepSpy,
  });

  assert.ok(typeof result === "object" && result !== null, "strategy must return an object");
  assert.ok(typeof result.clicks === "number", "result.clicks must be a number");
});

test("tiktok strategy: fixture contains view-more elements matching known selectors", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.tiktok.com/@user/video/123456789" });
  win.document.write(await readFixture("tiktok"));

  const clickSpy = makeClickAllMatchingSpy(win);
  const scrollSpy = makeScrollSpy();
  const waitSpy = makeWaitForSelectorSpy(win);
  const sleepSpy = makeSleepSpy();

  const strategies = await loadStrategyInContext(win, "content/sites/tiktok.js");

  await strategies["tiktok.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
    waitForSelector: waitSpy,
    sleep: sleepSpy,
  });

  const tiktokSelectors = [
    "div[data-e2e='view-more-comments']",
    "p[data-e2e='view-more-1']",
    "p[data-e2e='view-more-2']",
    "div[class*='DivViewMoreReplies']",
  ];
  const foundAny = tiktokSelectors.some((sel) => clickSpy.matched.some((m) => m.selector === sel));
  assert.ok(foundAny, `at least one tiktok view-more selector should find elements; matched: ${JSON.stringify(clickSpy.matched.map((m) => m.selector))}`);
});

test("x strategy: registers correct host keys", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://x.com/user/status/123456789" });
  win.document.write(await readFixture("x"));

  const strategies = await loadStrategyInContext(win, "content/sites/x.js");

  assert.ok("x.com" in strategies, "x.com key expected");
  assert.ok("twitter.com" in strategies, "twitter.com key expected");
});

test("x strategy: does not throw against fixture on a status page", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://x.com/user/status/123456789" });
  win.document.write(await readFixture("x"));

  const strategies = await loadStrategyInContext(win, "content/sites/x.js");

  const clickSpy = makeClickAllMatchingSpy(win);
  const scrollSpy = makeScrollSpy();

  const result = await strategies["x.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
  });

  assert.ok(typeof result === "object" && result !== null, "strategy must return an object");
  assert.ok(typeof result.clicks === "number", "result.clicks must be a number");
  assert.ok(typeof result.scrolls === "number", "result.scrolls must be a number");
});

test("x strategy: fixture contains elements matching show-reply selectors", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://x.com/user/status/123456789" });
  win.document.write(await readFixture("x"));

  const clickSpy = makeClickAllMatchingSpy(win);
  const scrollSpy = makeScrollSpy();

  const strategies = await loadStrategyInContext(win, "content/sites/x.js");

  await strategies["x.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
  });

  const xSelectors = [
    "button[role='button'] span, div[role='button'] span",
    "[data-testid='cellInnerDiv'] button span",
  ];
  const foundAny = xSelectors.some((sel) => clickSpy.matched.some((m) => m.selector === sel));
  assert.ok(foundAny, `at least one x.com selector should find elements in fixture; matched: ${JSON.stringify(clickSpy.matched.map((m) => m.selector))}`);
});

test("x strategy: does not scroll on non-status pages", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://x.com/home" });
  win.document.write("<html><body><div>Home feed</div></body></html>");

  const strategies = await loadStrategyInContext(win, "content/sites/x.js");

  let scrollCalled = false;
  const scrollSpy = async () => {
    scrollCalled = true;
    return { scrolls: 1, timed_out: false };
  };
  const clickSpy = makeClickAllMatchingSpy(win);

  await strategies["x.com"]({
    clickAllMatching: clickSpy,
    scrollToBottomIncremental: scrollSpy,
  });

  assert.equal(scrollCalled, false, "scrollToBottomIncremental should not be called on non-status pages");
});

test("linkedin strategy: registers correct host key", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.linkedin.com/feed/update/urn:li:activity:123/" });
  win.document.write(await readFixture("linkedin"));

  const strategies = await loadStrategyInContext(win, "content/sites/linkedin.js");

  assert.ok("linkedin.com" in strategies, "linkedin.com key expected");
});

test("linkedin strategy: does not throw against fixture and finds comment elements", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.linkedin.com/feed/update/urn:li:activity:123/" });
  win.document.write(await readFixture("linkedin"));

  const strategies = await loadStrategyInContext(win, "content/sites/linkedin.js");

  const clickSpy = makeClickAllMatchingSpy(win);
  const result = await strategies["linkedin.com"]({ clickAllMatching: clickSpy });

  assert.ok(typeof result === "object" && result !== null, "strategy must return an object");
  assert.ok(typeof result.clicks === "number", "result.clicks must be a number");
  assert.equal(result.scrolls, 0, "linkedin strategy always returns scrolls: 0");
  assert.ok(clickSpy.matched.length > 0, "at least one linkedin selector should match elements in fixture");
});

test("linkedin strategy: fixture contains load-more-comments button", async () => {
  const { Window } = loadHappyDom();
  const win = new Window({ url: "https://www.linkedin.com/feed/update/urn:li:activity:123/" });
  win.document.write(await readFixture("linkedin"));

  const clickSpy = makeClickAllMatchingSpy(win);

  const strategies = await loadStrategyInContext(win, "content/sites/linkedin.js");
  await strategies["linkedin.com"]({ clickAllMatching: clickSpy });

  const hasLoadMore = clickSpy.matched.some(
    (m) => m.selector === ".comments-comments-list__load-more-comments-button"
  );
  assert.ok(hasLoadMore, ".comments-comments-list__load-more-comments-button should find elements in fixture");
});

test("all site strategies: none throw when loaded against minimal empty document", async () => {
  const siteFiles = [
    { file: "content/sites/reddit.js", url: "https://www.reddit.com/r/test/comments/abc/title/", key: "reddit.com" },
    { file: "content/sites/youtube.js", url: "https://www.youtube.com/watch?v=test", key: "youtube.com" },
    { file: "content/sites/tiktok.js", url: "https://www.tiktok.com/@user/video/123", key: "tiktok.com" },
    { file: "content/sites/x.js", url: "https://x.com/user/status/123", key: "x.com" },
    { file: "content/sites/linkedin.js", url: "https://www.linkedin.com/feed/", key: "linkedin.com" },
  ];

  const { Window } = loadHappyDom();

  for (const { file, url, key } of siteFiles) {
    const win = new Window({ url });
    win.document.write("<html><body></body></html>");

    const strategies = await loadStrategyInContext(win, file);
    assert.ok(key in strategies, `${key} expected in strategies from ${file}`);

    const clickSpy = makeClickAllMatchingSpy(win);
    const scrollSpy = makeScrollSpy();
    const waitSpy = makeWaitForSelectorSpy(win);
    const sleepSpy = makeSleepSpy();

    await assert.doesNotReject(
      () =>
        strategies[key]({
          clickAllMatching: clickSpy,
          scrollToBottomIncremental: scrollSpy,
          waitForSelector: waitSpy,
          sleep: sleepSpy,
        }),
      `${key} strategy should not throw on empty document`
    );
  }
});
