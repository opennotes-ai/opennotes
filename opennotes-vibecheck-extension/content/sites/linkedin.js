(() => {
  const strategies = (globalThis.__vibecheckExpand_strategies ||= {});

  strategies["linkedin.com"] = async ({ clickAllMatching }) => {
    const expanded = await clickAllMatching([
      { selector: ".comments-comments-list__load-more-comments-button" },
      { selector: "button.show-prev-replies" },
      { selector: "button[aria-label*='Load more comments']" },
      { selector: "button[aria-label*='Load previous replies']" },
      { selector: "button.feed-shared-inline-show-more-text__see-more-less-toggle" },
      { selector: "button[class*='comments-comment-item__expand-button']" },
      {
        selector: "button",
        textPattern: /(\d+ more (replies|reply)|load more comments|load previous replies|see more)/i,
      },
    ]);

    return {
      ...expanded,
      scrolls: 0,
      error: expanded.clicks > 0 ? null : "selector-exhausted",
      retryable: false,
    };
  };
})();
