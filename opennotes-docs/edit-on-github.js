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
   - API Reference endpoint pages (e.g. /api-reference/public/list-requests)
     are generated from openapi-public.json and have no .mdx source. We skip
     injection on /api-reference/<slug> paths that don't match a known
     hand-authored MDX file. */

(function () {
  if (typeof window === "undefined") return;

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

  function pathToSourceUrl(pathname) {
    if (!MDX_PAGES.has(pathname)) return null;
    return REPO_BASE + pathname + ".mdx";
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
    var existing = document.querySelector("[data-edit-on-github]");
    if (existing) existing.remove();

    var url = pathToSourceUrl(window.location.pathname);
    if (!url) return;

    var mount = findMountPoint();
    if (!mount) return;

    var link = buildLink(url);
    if (mount.position === "before") {
      mount.node.parentNode.insertBefore(link, mount.node);
    } else {
      mount.node.appendChild(link);
    }
  }

  function scheduleInject() {
    // Mintlify's MDX render lands after route change; wait briefly for the
    // DOM, then poll a few times in case React is mid-rerender.
    var attempts = 0;
    var timer = setInterval(function () {
      inject();
      attempts++;
      if (attempts >= 6 || document.querySelector("[data-edit-on-github]")) {
        clearInterval(timer);
      }
    }, 150);
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
