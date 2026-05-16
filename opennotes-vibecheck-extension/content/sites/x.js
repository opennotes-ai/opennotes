(() => {
  const strategies = (globalThis.__vibecheckExpand_strategies ||= {});

  const xStrategy = async ({ clickAllMatching, scrollToBottomIncremental }) => {
    const isStatus = /^[/][^/]+\/status\/\d+/.test(location.pathname);
    const scrolled = isStatus
      ? await scrollToBottomIncremental({
          stepPx: window.innerHeight || 800,
          deadlineMs: 10_000,
        })
      : { scrolls: 0, timed_out: false };

    const expanded = await clickAllMatching([
      {
        selector: "button[role='button'] span, div[role='button'] span",
        textPattern: /^(show( more)? replies|show this thread|show \d+ more)$/i,
        closestClickable: true,
      },
      {
        selector: "[data-testid='cellInnerDiv'] button:not([data-testid='tweet-text-show-more-link']) span",
        textPattern: /show/i,
        closestClickable: true,
      },
    ]);

    return {
      ...expanded,
      scrolls: scrolled.scrolls,
      timed_out: scrolled.timed_out || expanded.timed_out,
      error: expanded.clicks + scrolled.scrolls > 0 ? null : "selector-exhausted",
      retryable: false,
    };
  };

  strategies["x.com"] = xStrategy;
  strategies["twitter.com"] = xStrategy;
})();
