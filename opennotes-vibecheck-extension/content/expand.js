(() => {
  const DEFAULT_DEADLINE_MS = 25_000;
  const DEFAULT_MAX_ITERATIONS = 50;
  const DEFAULT_MUTATION_QUIET_MS = 300;
  const DEFAULT_SETTLE_MS = 200;
  const DEFAULT_STEP_PX = 800;

  const strategies = (globalThis.__vibecheckExpand_strategies ||= {});

  globalThis.__vibecheckExpand_run = async (opts = {}) => {
    const startedAt = now();
    const host = location.hostname;
    const deadlineMs = Number(opts.deadlineMs ?? DEFAULT_DEADLINE_MS);
    const deadline = startedAt + deadlineMs;
    const match = findStrategy(host, strategies);

    if (!match) {
      return {
        site: host,
        iterations: 0,
        clicks: 0,
        useful_clicks: 0,
        scrolls: 0,
        duration_ms: elapsed(startedAt),
        timed_out: false,
        error: "no-strategy",
        status: "unsupported",
        retryable: false,
      };
    }

    try {
      const helpers = createHelpers({ deadline, opts });
      const strategyResult = await withDeadline(Promise.resolve(match.strategy(helpers)), deadline);
      return buildResult(match.site, startedAt, strategyResult, false, null);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const timedOut = message === "expand-deadline";
      return buildResult(match.site, startedAt, {}, timedOut, message);
    }
  };

  function findStrategy(host, registry) {
    return Object.entries(registry)
      .sort(([left], [right]) => right.length - left.length)
      .map(([site, strategy]) => ({ site, strategy }))
      .find(({ site }) => host === site || host.endsWith(`.${site}`));
  }

  function createHelpers({ deadline, opts }) {
    const scopedOptions = (options = {}) => {
      const optionDeadline = options.deadlineMs
        ? Math.min(deadline, now() + Number(options.deadlineMs))
        : deadline;
      return { ...opts, ...options, deadline: options.deadline ?? optionDeadline };
    };

    return {
      deadline,
      timeRemainingMs: () => Math.max(0, deadline - now()),
      clickAllMatching: (specs, options = {}) =>
        clickAllMatching(specs, scopedOptions(options)),
      scrollToBottomIncremental: (options = {}) =>
        scrollToBottomIncremental(scopedOptions(options)),
      waitForSelector: (selector, options = {}) =>
        waitForSelector(selector, scopedOptions(options)),
      sleep,
    };
  }

  async function clickAllMatching(rawSpecs, options = {}) {
    const specs = normalizeClickSpecs(rawSpecs);
    const maxIterations = Number(options.maxIterations ?? DEFAULT_MAX_ITERATIONS);
    const deadline = options.deadline ?? now() + Number(options.deadlineMs ?? DEFAULT_DEADLINE_MS);
    const scope = options.scope ?? null;
    let clicks = 0;
    let usefulClicks = 0;
    let iterations = 0;

    while (iterations < maxIterations && now() < deadline) {
      iterations += 1;
      let passClicks = 0;

      for (const spec of specs) {
        const candidates = queryAll(spec.selector);
        for (const candidate of candidates) {
          if (now() >= deadline) {
            return { clicks, useful_clicks: usefulClicks, iterations, timed_out: true };
          }

          const target = resolveClickTarget(candidate, spec);
          if (!target || !isVisibleEnabled(target) || !matchesText(candidate, spec)) {
            continue;
          }
          if (spec.predicate && !spec.predicate(candidate, target)) {
            continue;
          }

          const before = domSignature();
          target.click();
          clicks += 1;
          passClicks += 1;
          await waitForQuiescence({
            deadline,
            mutationQuietMs: options.mutationQuietMs,
            settleMs: options.settleMs,
            scope,
          });
          if (domSignature() !== before) {
            usefulClicks += 1;
          }
        }
      }

      if (passClicks === 0) {
        break;
      }
    }

    return {
      clicks,
      useful_clicks: usefulClicks,
      iterations,
      timed_out: now() >= deadline || iterations >= maxIterations,
    };
  }

  async function scrollToBottomIncremental(options = {}) {
    const target = options.target || window;
    const stepPx = Number(options.stepPx ?? DEFAULT_STEP_PX);
    const deadline = options.deadline ?? now() + Number(options.deadlineMs ?? DEFAULT_DEADLINE_MS);
    let scrolls = 0;
    let stableSteps = 0;
    let previousHeight = getScrollHeight(target);

    while (stableSteps < 2 && now() < deadline) {
      const currentTop = getScrollTop(target);
      scrollTo(target, currentTop + stepPx);
      scrolls += 1;

      await waitForQuiescence({
        deadline,
        mutationQuietMs: options.mutationQuietMs,
        settleMs: options.settleMs,
      });

      const nextHeight = getScrollHeight(target);
      stableSteps = nextHeight > previousHeight ? 0 : stableSteps + 1;
      previousHeight = nextHeight;

      if (getScrollTop(target) + getViewportHeight(target) >= nextHeight) {
        stableSteps += 1;
      }
    }

    return {
      scrolls,
      timed_out: now() >= deadline,
    };
  }

  async function waitForSelector(selector, options = {}) {
    const deadline = options.deadline ?? now() + Number(options.deadlineMs ?? 2_000);
    while (now() < deadline) {
      const element = document.querySelector(selector);
      if (element && isVisibleEnabled(element)) {
        return element;
      }
      await sleep(Number(options.pollMs ?? 100));
    }
    return null;
  }

  function buildResult(site, startedAt, rawResult = {}, forcedTimeout, forcedError) {
    const clicks = Number(rawResult.clicks) || 0;
    const usefulClicks = Number(rawResult.useful_clicks ?? rawResult.usefulClicks) || 0;
    const scrolls = Number(rawResult.scrolls) || 0;
    const iterations = Number(rawResult.iterations) || 0;
    const timedOut = Boolean(forcedTimeout || rawResult.timed_out);
    const error = forcedError || rawResult.error || null;
    const usefulWork = clicks + scrolls > 0;
    const status = deriveStatus({ error, timedOut, usefulWork });

    return {
      site,
      iterations,
      clicks,
      useful_clicks: usefulClicks,
      scrolls,
      duration_ms: elapsed(startedAt),
      timed_out: timedOut,
      error,
      status,
      retryable: status === "failure" ? Boolean(rawResult.retryable ?? forcedError) : false,
    };
  }

  function deriveStatus({ error, timedOut, usefulWork }) {
    if (!error && !timedOut && usefulWork) {
      return "success";
    }
    if ((timedOut || error) && usefulWork) {
      return "partial";
    }
    return "failure";
  }

  async function waitForQuiescence(options) {
    const mutationQuietMs = Number(options.mutationQuietMs ?? DEFAULT_MUTATION_QUIET_MS);
    const settleMs = Number(options.settleMs ?? DEFAULT_SETTLE_MS);
    if (mutationQuietMs <= 0) {
      await sleepUntilDeadline(settleMs, options.deadline);
      return;
    }

    await new Promise((resolve) => {
      let timer = null;
      let observer = null;
      const finish = () => {
        if (timer) {
          clearTimeout(timer);
        }
        if (observer) {
          observer.disconnect();
        }
        resolve();
      };
      const schedule = () => {
        if (timer) {
          clearTimeout(timer);
        }
        timer = setTimeout(finish, Math.min(mutationQuietMs, Math.max(0, options.deadline - now())));
      };

      if (typeof MutationObserver === "function") {
        observer = new MutationObserver(schedule);
        const observeTarget = (options.scope && typeof options.scope === "object" && options.scope.nodeType) ? options.scope : document.documentElement;
        observer.observe(observeTarget, { childList: true, subtree: true });
      }
      schedule();
    });

    await sleepUntilDeadline(settleMs, options.deadline);
  }

  function normalizeClickSpecs(rawSpecs) {
    return (Array.isArray(rawSpecs) ? rawSpecs : [rawSpecs]).map((spec) =>
      typeof spec === "string" ? { selector: spec } : spec
    );
  }

  function queryAll(selector) {
    try {
      return Array.from(document.querySelectorAll(selector));
    } catch {
      return [];
    }
  }

  function resolveClickTarget(candidate, spec) {
    if (!spec.closestClickable) {
      return candidate;
    }
    return candidate.closest?.("button,a,[role='button'],[tabindex]") || candidate;
  }

  function isVisibleEnabled(element) {
    const style = typeof getComputedStyle === "function" ? getComputedStyle(element) : null;
    return (
      element.offsetParent !== null &&
      !element.disabled &&
      element.getAttribute?.("aria-disabled") !== "true" &&
      style?.visibility !== "hidden" &&
      style?.display !== "none"
    );
  }

  function matchesText(candidate, spec) {
    if (!spec.textPattern) {
      return true;
    }
    return spec.textPattern.test(candidate.textContent || "");
  }

  function domSignature() {
    return [
      document.documentElement?.scrollHeight || 0,
      document.body?.children?.length || 0,
    ].join(":");
  }

  function getScrollTop(target) {
    return target === window ? window.scrollY || document.documentElement.scrollTop || 0 : target.scrollTop || 0;
  }

  function getScrollHeight(target) {
    if (target === window) {
      return Math.max(
        document.documentElement?.scrollHeight || 0,
        document.body?.scrollHeight || 0
      );
    }
    return target.scrollHeight || 0;
  }

  function getViewportHeight(target) {
    return target === window ? window.innerHeight || document.documentElement.clientHeight || 0 : target.clientHeight || 0;
  }

  function scrollTo(target, top) {
    if (target === window) {
      window.scrollTo(0, top);
      return;
    }
    if (typeof target.scrollTo === "function") {
      target.scrollTo({ top });
    } else {
      target.scrollTop = top;
    }
  }

  async function withDeadline(promise, deadline) {
    const remaining = Math.max(0, deadline - now());
    let timer = null;
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error("expand-deadline")), remaining);
        }),
      ]);
    } finally {
      if (timer) {
        clearTimeout(timer);
      }
    }
  }

  async function sleepUntilDeadline(ms, deadline) {
    await sleep(Math.min(Math.max(0, ms), Math.max(0, deadline - now())));
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function now() {
    return typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();
  }

  function elapsed(startedAt) {
    return Math.max(0, Math.round(now() - startedAt));
  }
})();
