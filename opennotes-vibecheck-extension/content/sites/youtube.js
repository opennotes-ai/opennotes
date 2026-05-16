(() => {
  const strategies = (globalThis.__vibecheckExpand_strategies ||= {});

  strategies["youtube.com"] = async ({
    clickAllMatching,
    scrollToBottomIncremental,
    waitForSelector,
  }) => {
    const comments = document.querySelector("#comments");
    comments?.scrollIntoView?.({ block: "start" });

    const initialScroll = await scrollToBottomIncremental({
      stepPx: window.innerHeight || 800,
      deadlineMs: 5_000,
    });
    const commentsLoaded =
      document.querySelector("ytd-comments") ||
      document.querySelector("ytd-item-section-renderer") ||
      (await waitForSelector("ytd-comments, ytd-item-section-renderer", { deadlineMs: 1_500 }));

    if (!commentsLoaded) {
      return {
        clicks: 0,
        useful_clicks: 0,
        scrolls: initialScroll.scrolls,
        iterations: 0,
        timed_out: initialScroll.timed_out,
        error: "no-comments",
        retryable: false,
      };
    }

    const expanded = await clickAllMatching([
      { selector: "ytd-comment-replies-renderer #more-replies button" },
      { selector: "ytd-continuation-item-renderer button" },
      { selector: "tp-yt-paper-button#more" },
      { selector: "ytd-button-renderer#more-replies button" },
      { selector: "#button[aria-label^='Show more']" },
      { selector: "button", textPattern: /^(show more|view \d+ replies|show more replies)$/i },
    ]);

    return {
      ...expanded,
      scrolls: initialScroll.scrolls,
      timed_out: initialScroll.timed_out || expanded.timed_out,
      error: expanded.clicks + initialScroll.scrolls > 0 ? null : "selector-exhausted",
      retryable: false,
    };
  };
})();
