(() => {
  const strategies = (globalThis.__vibecheckExpand_strategies ||= {});

  strategies["tiktok.com"] = async ({
    clickAllMatching,
    scrollToBottomIncremental,
    waitForSelector,
    sleep,
  }) => {
    let commentList =
      document.querySelector("[data-e2e='comment-list']") ||
      document.querySelector("div[class*='DivCommentListContainer']");

    if (!commentList) {
      const opener = document.querySelector("button[data-e2e='comment-icon']");
      if (opener && opener.offsetParent !== null) {
        opener.click();
        await sleep(250);
      }
      commentList =
        (await waitForSelector("[data-e2e='comment-list']", { deadlineMs: 2_000 })) ||
        (await waitForSelector("div[class*='DivCommentListContainer']", { deadlineMs: 500 }));
    }

    if (!commentList) {
      return {
        clicks: 0,
        useful_clicks: 0,
        scrolls: 0,
        iterations: 0,
        timed_out: false,
        error: "drawer-unavailable",
        retryable: false,
      };
    }

    const scrolled = await scrollToBottomIncremental({
      target: commentList,
      stepPx: Math.max(400, commentList.clientHeight || 600),
      deadlineMs: 5_000,
    });
    const expanded = await clickAllMatching(
      [
        { selector: "[data-e2e='view-more-comments']", closestClickable: true },
        { selector: "[data-e2e='view-more-reply']", closestClickable: true },
        { selector: "div[data-e2e='view-more-comments']", closestClickable: true },
        { selector: "p[data-e2e='view-more-1']", closestClickable: true },
        { selector: "p[data-e2e='view-more-2']", closestClickable: true },
        { selector: "div[class*='DivViewMoreReplies']", closestClickable: true },
        { selector: "button, div[role='button'], p", textPattern: /^view .*more/i, closestClickable: true },
      ],
      { scope: commentList }
    );

    return {
      ...expanded,
      scrolls: scrolled.scrolls,
      timed_out: scrolled.timed_out || expanded.timed_out,
      error: expanded.clicks + scrolled.scrolls > 0 ? null : "selector-exhausted",
      retryable: false,
    };
  };
})();
