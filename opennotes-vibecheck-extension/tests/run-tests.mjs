import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

const EXTENSION_DIR = new URL("../", import.meta.url);

async function readExtensionFile(path) {
  return readFile(new URL(path, EXTENSION_DIR), "utf8");
}

function createRunnerContext({ hostname = "example.com", pathname = "/" } = {}) {
  const context = {
    console,
    globalThis: {},
    location: { hostname, pathname },
    performance: { now: () => Date.now() },
    setTimeout,
    clearTimeout,
    Element: class Element {},
  };
  context.window = {
    innerHeight: 800,
    scrollY: 0,
    scrollHeight: 1000,
    scrollTo: (_x, y) => {
      context.window.scrollY = y;
    },
    getComputedStyle: () => ({ visibility: "visible", display: "block" }),
  };
  context.document = {
    documentElement: { scrollHeight: 1000 },
    body: { scrollHeight: 1000 },
    querySelectorAll: () => [],
  };
  context.globalThis = context;
  return vm.createContext(context);
}

async function installRunner(context) {
  const source = await readExtensionFile("content/expand.js");
  vm.runInContext(source, context, { filename: "content/expand.js" });
  assert.equal(typeof context.__vibecheckExpand_run, "function");
}

test("popup renders and persists the expand-all-comments setting", async () => {
  const [html, js, css] = await Promise.all([
    readExtensionFile("popup.html"),
    readExtensionFile("popup.js"),
    readExtensionFile("popup.css"),
  ]);

  assert.match(html, /id="submit-btn"[\s\S]*id="expand-all-comments"/);
  assert.match(html, /<input[^>]+id="expand-all-comments"[^>]+type="checkbox"/);
  assert.match(html, /Expand all comments/);
  assert.match(js, /expandAllComments:\s*"vibecheck_expand_all_comments"/);
  assert.match(js, /chrome\.storage\.sync\.get\([\s\S]*STORAGE_KEYS\.expandAllComments/);
  assert.match(js, /chrome\.storage\.sync\.set\([\s\S]*STORAGE_KEYS\.expandAllComments/);
  assert.match(css, /\.expand-toggle/);
});

test("expand runner reports unsupported sites without throwing", async () => {
  const context = createRunnerContext({ hostname: "unsupported.example" });

  await installRunner(context);
  const result = await context.__vibecheckExpand_run({ mutationQuietMs: 0, settleMs: 0 });

  assert.equal(result.site, "unsupported.example");
  assert.equal(result.status, "unsupported");
  assert.equal(result.error, "no-strategy");
  assert.equal(result.retryable, false);
  assert.equal(result.clicks, 0);
  assert.equal(result.scrolls, 0);
});

test("expand runner matches host suffixes on dot boundaries", async () => {
  const context = createRunnerContext({ hostname: "sub.example.com" });
  context.__vibecheckExpand_strategies = {
    "example.com": async () => ({
      clicks: 1,
      useful_clicks: 1,
      scrolls: 0,
      iterations: 1,
      timed_out: false,
      error: null,
    }),
    "ample.com": async () => ({
      clicks: 99,
      useful_clicks: 99,
      scrolls: 0,
      iterations: 1,
      timed_out: false,
      error: null,
    }),
  };

  await installRunner(context);
  const result = await context.__vibecheckExpand_run({ mutationQuietMs: 0, settleMs: 0 });

  assert.equal(result.site, "example.com");
  assert.equal(result.status, "success");
  assert.equal(result.clicks, 1);
  assert.equal(result.useful_clicks, 1);
});

test("clickAllMatching clicks visible enabled targets and tracks useful DOM changes", async () => {
  const clicked = [];
  let queryCount = 0;
  const context = createRunnerContext({ hostname: "example.com" });
  const target = {
    textContent: "Show more replies",
    disabled: false,
    offsetParent: {},
    getAttribute: () => null,
    matches: (selector) => selector === "button",
    closest: () => target,
    click: () => {
      clicked.push("target");
      context.document.querySelectorAll = () => [];
      context.document.documentElement.scrollHeight += 10;
    },
  };
  context.document.querySelectorAll = () => {
    queryCount += 1;
    return queryCount === 1 ? [target] : [];
  };
  context.__vibecheckExpand_strategies = {
    "example.com": async ({ clickAllMatching }) =>
      clickAllMatching([{ selector: "button", textPattern: /show more replies/i }], {
        maxIterations: 5,
        mutationQuietMs: 0,
        settleMs: 0,
      }),
  };

  await installRunner(context);
  const result = await context.__vibecheckExpand_run({ mutationQuietMs: 0, settleMs: 0 });

  assert.deepEqual(clicked, ["target"]);
  assert.equal(result.status, "success");
  assert.equal(result.clicks, 1);
  assert.equal(result.useful_clicks, 1);
  assert.equal(result.iterations, 2);
});

test("site strategy files register the planned host keys", async () => {
  const expected = {
    "content/sites/youtube.js": ["youtube.com"],
    "content/sites/reddit.js": ["reddit.com", "old.reddit.com"],
    "content/sites/tiktok.js": ["tiktok.com"],
    "content/sites/x.js": ["x.com", "twitter.com"],
    "content/sites/linkedin.js": ["linkedin.com"],
  };

  for (const [path, keys] of Object.entries(expected)) {
    const source = await readExtensionFile(path);
    for (const key of keys) {
      assert.match(source, new RegExp(`__vibecheckExpand_strategies[\\s\\S]*\\["${key}"\\]`));
    }
  }
});

test("reddit strategy skips non-http inline-more href schemes", async () => {
  const context = vm.createContext({
    globalThis: {},
    location: {
      href: "https://old.reddit.com/r/example/comments/abc/title/",
      hostname: "old.reddit.com",
      pathname: "/r/example/comments/abc/title/",
    },
    URL,
  });
  context.globalThis = context;
  const source = await readExtensionFile("content/sites/reddit.js");
  vm.runInContext(source, context, { filename: "content/sites/reddit.js" });

  let oldRedditSpec = null;
  await context.__vibecheckExpand_strategies["old.reddit.com"]({
    clickAllMatching: async (specs) => {
      oldRedditSpec = specs.find((spec) => spec.selector === ".morechildren a");
      return { clicks: 0, useful_clicks: 0, iterations: 1, timed_out: false };
    },
  });

  const candidate = (href) => ({
    getAttribute: () => href,
    closest: (selector) => selector === ".sitetable",
  });

  assert.equal(oldRedditSpec.predicate(candidate("data:text/html,<p>x</p>")), false);
  assert.equal(oldRedditSpec.predicate(candidate("vbscript:msgbox(1)")), false);
  assert.equal(oldRedditSpec.predicate(candidate("javascript:void(0)")), false);
  assert.equal(
    oldRedditSpec.predicate(
      candidate("https://old.reddit.com/r/example/comments/abc/title/?count=500")
    ),
    true
  );
});

test("submit flow injects expansion before capture and emits one telemetry event", async () => {
  const js = await readExtensionFile("popup.js");

  assert.match(js, /async function runExpansion\(tabId\)/);
  assert.match(js, /const EXPANSION_FILES = \[[\s\S]*content\/sites\/reddit\.js[\s\S]*content\/expand\.js[\s\S]*\]/);
  assert.match(js, /files:\s*EXPANSION_FILES/);
  assert.match(js, /func:\s*\(\)\s*=>\s*globalThis\.__vibecheckExpand_run\(\)/);
  assert.match(js, /event:\s*"vibecheck\.extension\.expand_pass"/);
  assert.match(js, /attempts/);
  assert.match(js, /renderExpandStatus\(expandResult\)/);

  const expansionIndex = js.indexOf("await runExpansion(activeTab.id)");
  const captureIndex = js.indexOf("await capturePage(activeTab.id)");
  assert.ok(expansionIndex > -1, "submitCurrentPage should await runExpansion");
  assert.ok(captureIndex > -1, "submitCurrentPage should still capture the page");
  assert.ok(expansionIndex < captureIndex, "expansion should happen before capturePage");
});
