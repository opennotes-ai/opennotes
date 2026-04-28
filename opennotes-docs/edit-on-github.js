/* Per-page "Edit on GitHub" affordance for docs.opennotes.ai.

   Mintlify auto-loads any .js file in the project root on every page. It does
   not provide a native page-aware Edit-on-GitHub feature, so this script
   injects one above the prev/next pagination footer, deriving the source MDX
   path from window.location.pathname.

   Notes:
   - Mintlify is a Next.js SPA: pushState navigation does not reload this
     script, so we hook history events and re-inject on every URL change.
   - We mark the injected node with [data-edit-on-github] and replace it on
     each navigation, so we never duplicate.
   - Idempotence: a window-level guard prevents history.pushState/replaceState
     wrappers from stacking if the script is evaluated more than once (HMR,
     hot reload, future Mintlify loader changes).
   - SPA route-change race: after navigation, React rerenders the page content
     asynchronously. We poll for ~1s post-navigation AND attach a
     MutationObserver that re-injects if our node is removed by a later
     rerender.
   - API Reference endpoint pages (e.g. /api-reference/public/list-requests)
     are generated from openapi-public.json and have no .mdx source. We skip
     injection on paths that don't match the hand-authored MDX allowlist. */

(function () {
  if (typeof window === "undefined") return;
  if (window.__opennotesEditOnGithubInstalled) return;
  window.__opennotesEditOnGithubInstalled = true;

  var REPO_BASE = "https://github.com/opennotes-ai/opennotes/edit/main/opennotes-docs";

  // Pages with hand-authored MDX. Anything outside this set is skipped (it's
  // either an OpenAPI-generated page or an unknown path).
  var MDX_PAGES = new Set([
    "/introduction",
    "/integration-guide/overview",
    "/integration-guide/quickstart",
    "/integration-guide/onboarding/register-community",
    "/integration-guide/onboarding/manage-instances",
    "/integration-guide/onboarding/api-keys",
    "/integration-guide/onboarding/configure-tiers",
    "/integration-guide/concepts/headers-and-auth",
    "/integration-guide/concepts/scopes",
    "/integration-guide/concepts/errors",
    "/integration-guide/concepts/webhooks",
    "/integration-guide/walkthrough/index",
    "/integration-guide/walkthrough/01-identify-user",
    "/integration-guide/walkthrough/02-identify-community",
    "/integration-guide/walkthrough/03-submit-request",
    "/integration-guide/walkthrough/04-handle-action",
    "/integration-guide/walkthrough/05-webhooks-and-retries",
    "/existing-integrations/overview",
    "/existing-integrations/discourse/overview",
    "/existing-integrations/discourse/install",
    "/existing-integrations/discourse/configure",
    "/existing-integrations/discourse/upgrade",
    "/existing-integrations/discourse/troubleshoot",
    "/existing-integrations/discourse/user-guide",
    "/existing-integrations/discourse/architecture",
    "/api-reference/overview",
    "/api-reference/authentication",
    "/api-reference/conventions",
  ]);

  function normalizePath(pathname) {
    if (!pathname || pathname === "/") return "/introduction";
    return pathname.length > 1 && pathname.endsWith("/")
      ? pathname.slice(0, -1)
      : pathname;
  }

  function pathToSourceUrl(pathname) {
    var p = normalizePath(pathname);
    if (!MDX_PAGES.has(p)) return null;
    return REPO_BASE + p + ".mdx";
  }

  function findMountPoint() {
    // Inject above the prev/next pagination footer when present; otherwise
    // append to the prose container.
    var pagination = document.getElementById("pagination");
    if (pagination && pagination.parentNode) {
      return { node: pagination, position: "before" };
    }
    var prose = document.querySelector(".mdx-content");
    if (prose) return { node: prose, position: "append" };
    return null;
  }

  function buildLink(href) {
    var wrapper = document.createElement("div");
    wrapper.setAttribute("data-edit-on-github", "");
    wrapper.style.cssText = "margin-top:2rem;font-size:0.875rem;";
    var a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "Edit this page on GitHub";
    a.className = "link";
    a.style.cssText = "color:rgb(75,85,99);font-weight:500;";
    wrapper.appendChild(a);
    return wrapper;
  }

  function inject() {
    var url = pathToSourceUrl(window.location.pathname);
    if (!url) {
      // Path is not in the MDX allowlist (e.g. OpenAPI-generated page) —
      // remove any stale link from a prior in-allowlist page.
      var stale = document.querySelector("[data-edit-on-github]");
      if (stale) stale.remove();
      return;
    }

    // If a link already exists with the right href, leave it alone.
    var existing = document.querySelector("[data-edit-on-github] a");
    if (existing && existing.href === url) return;

    var oldWrapper = document.querySelector("[data-edit-on-github]");
    if (oldWrapper) oldWrapper.remove();

    var mount = findMountPoint();
    if (!mount) return;

    var link = buildLink(url);
    if (mount.position === "before") {
      mount.node.parentNode.insertBefore(link, mount.node);
    } else {
      mount.node.appendChild(link);
    }
  }

  // Poll briefly post-navigation: React often replaces the page content
  // asynchronously, so a single inject() right after pushState may land
  // before the new <div id="pagination"> mounts (or be wiped by the rerender
  // immediately after). Run all attempts; inject() is idempotent.
  function scheduleInject() {
    var attempts = 0;
    var timer = setInterval(function () {
      inject();
      attempts++;
      if (attempts >= 8) clearInterval(timer);
    }, 150);
  }

  // MutationObserver re-injects after the polling window if Mintlify's React
  // tree replaces the content area. Watches the body for child-list changes;
  // re-runs inject() when our wrapper is missing from the current page.
  var observer = new MutationObserver(function () {
    if (!document.querySelector("[data-edit-on-github]")) {
      inject();
    }
  });
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }

  // Patch history to re-inject on SPA navigation.
  var origPush = history.pushState;
  var origReplace = history.replaceState;
  history.pushState = function () {
    var ret = origPush.apply(this, arguments);
    scheduleInject();
    return ret;
  };
  history.replaceState = function () {
    var ret = origReplace.apply(this, arguments);
    scheduleInject();
    return ret;
  };
  window.addEventListener("popstate", scheduleInject);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleInject);
  } else {
    scheduleInject();
  }
})();
