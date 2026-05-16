(() => {
  const strategies = (globalThis.__vibecheckExpand_strategies ||= {});

  const redditStrategy = async ({ clickAllMatching }) => {
    const expanded = await clickAllMatching([
      {
        selector: "shreddit-comment-tree faceplate-partial[loading='action']",
        closestClickable: true,
      },
      {
        selector: "shreddit-comment button[slot='more-comments-button']",
      },
      {
        selector: "button",
        textPattern: /^(view|show|load) .*(more comments|more replies|replies)$/i,
      },
      {
        selector: ".morechildren a",
        textPattern: /(more replies|load more comments)/i,
        predicate: isSafeOldRedditInlineMoreLink,
      },
    ]);

    return {
      ...expanded,
      scrolls: 0,
      error: expanded.clicks > 0 ? null : "selector-exhausted",
      retryable: false,
    };
  };

  strategies["old.reddit.com"] = redditStrategy;
  strategies["reddit.com"] = redditStrategy;

  function isSafeOldRedditInlineMoreLink(candidate) {
    const href = candidate.getAttribute?.("href") || "";
    if (!href || href.startsWith("#")) {
      return true;
    }

    try {
      const link = new URL(href, location.href);
      return (
        (link.protocol === "https:" || link.protocol === "http:") &&
        link.hostname === location.hostname &&
        link.pathname === location.pathname &&
        candidate.closest?.(".sitetable")
      );
    } catch {
      return false;
    }
  }
})();
