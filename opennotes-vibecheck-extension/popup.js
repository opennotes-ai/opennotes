const BASE_URL = "https://vibecheck.opennotes.ai";

const STORAGE_KEYS = {
  apiKey: "vibecheck_api_key",
  expandAllComments: "vibecheck_expand_all_comments",
};

const EXPANSION_FILES = [
  "content/sites/reddit.js",
  "content/sites/youtube.js",
  "content/sites/tiktok.js",
  "content/sites/linkedin.js",
  "content/sites/x.js",
  "content/expand.js",
];

const apiKeyInput = document.querySelector("#api-key");
const currentUrlInput = document.querySelector("#current-url");
const submitButton = document.querySelector("#submit-btn");
const expandCheckbox = document.querySelector("#expand-all-comments");
const statusEl = document.querySelector("#status");
const resultSection = document.querySelector("#result");
const resultContent = document.querySelector("#result-content");
const expandStatus = document.querySelector("#expand-status");
const requestEmailInput = document.querySelector("#request-email");
const requestKeyButton = document.querySelector("#request-key-btn");
const requestStatusEl = document.querySelector("#request-status");

const MAX_SCREENSHOT_BASE64_LENGTH = 20 * 1024 * 1024;

let activeTab = null;

document.addEventListener("DOMContentLoaded", async () => {
  chrome.storage.sync.remove(["vibecheck_endpoint_url"]);
  await loadSettings();
  await loadActiveTab();
});

apiKeyInput.addEventListener("change", saveSettings);
apiKeyInput.addEventListener("blur", saveSettings);
expandCheckbox.addEventListener("change", () => {
  saveExpandPref();
  if (!expandCheckbox.checked) {
    hideExpandStatus();
  }
});
submitButton.addEventListener("click", submitCurrentPage);
requestKeyButton.addEventListener("click", handleRequestApiKey);

async function loadSettings() {
  const settings = await chrome.storage.sync.get([
    STORAGE_KEYS.apiKey,
    STORAGE_KEYS.expandAllComments,
  ]);

  apiKeyInput.value = settings[STORAGE_KEYS.apiKey] || "";
  expandCheckbox.checked = Boolean(settings[STORAGE_KEYS.expandAllComments]);
}

async function saveSettings() {
  await chrome.storage.sync.set({
    [STORAGE_KEYS.apiKey]: apiKeyInput.value.trim(),
  });
}

async function saveExpandPref() {
  await chrome.storage.sync.set({
    [STORAGE_KEYS.expandAllComments]: expandCheckbox.checked,
  });
}

async function loadActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  activeTab = tab || null;
  currentUrlInput.value = activeTab?.url || "";

  if (!activeTab?.id || !activeTab?.url) {
    setStatus("No active page is available.");
    submitButton.disabled = true;
  }
}

async function submitCurrentPage() {
  if (submitButton.disabled) {
    return;
  }
  submitButton.disabled = true;

  hideResult();
  hideExpandStatus();
  const apiKey = apiKeyInput.value.trim();
  const shouldExpandComments = expandCheckbox.checked;

  try {
    if (!apiKey) {
      showError("Missing API key", "Configure the API key in settings.");
      return;
    }

    if (!activeTab?.id || !activeTab?.url) {
      showError("No active page", "Open a browser tab before submitting.");
      return;
    }

    const scrapeUrl = buildScrapeUrl();

    await saveSettings();
    let expandResult = null;

    try {
      if (shouldExpandComments) {
        setPhase("expanding");
        expandResult = await runExpansion(activeTab.id);
      }

      setPhase("capturing");
      const page = await capturePage(activeTab.id);
      const screenshotBase64 = await captureScreenshotForSubmission(activeTab.id);
      const body = compactPayload({
        url: activeTab.url,
        source_url: activeTab.url,
        html: page.html,
        title: page.title,
        description: page.description,
        screenshot_base64: screenshotBase64,
      });

      setPhase("submitting");
      const response = await fetch(scrapeUrl, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      const responseBody = await readResponseBody(response);

      if (!response.ok) {
        showError(`HTTP ${response.status}`, formatErrorBody(responseBody));
        renderExpandStatus(expandResult);
        return;
      }

      showSuccess(responseBody);
      renderExpandStatus(expandResult);
    } catch (error) {
      showError("Network error", error instanceof Error ? error.message : String(error));
      renderExpandStatus(expandResult);
    } finally {
      setPhase("idle");
    }
  } finally {
    submitButton.disabled = false;
  }
}

async function handleRequestApiKey() {
  const email = requestEmailInput.value.trim();

  if (!requestEmailInput.checkValidity() || !/.+@.+\..+/.test(email)) {
    requestEmailInput.reportValidity();
    return;
  }

  requestKeyButton.disabled = true;
  setRequestStatus("", false);

  try {
    const response = await fetch(`${BASE_URL}/api/keys/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (response.ok) {
      setRequestStatus("Check your email for the API key", false);
      return;
    }

    if (response.status === 429) {
      setRequestStatus("Too many requests. Please try again later.", true);
      return;
    }

    if (response.status >= 500) {
      setRequestStatus("Service temporarily unavailable. Please try again.", true);
      return;
    }

    if (response.status === 400) {
      let message = "Invalid request.";
      try {
        const body = await response.json();
        if (body?.message) {
          message = body.message;
        }
      } catch {
      }
      setRequestStatus(message, true);
      return;
    }

    setRequestStatus("Something went wrong. Please try again.", true);
  } catch {
    setRequestStatus("Could not reach the server. Check your connection.", true);
  } finally {
    requestKeyButton.disabled = false;
  }
}

function setRequestStatus(message, isError) {
  if (!message) {
    requestStatusEl.hidden = true;
    requestStatusEl.textContent = "";
    requestStatusEl.classList.remove("request-status--error", "request-status--success");
    return;
  }
  requestStatusEl.textContent = message;
  requestStatusEl.classList.toggle("request-status--error", isError);
  requestStatusEl.classList.toggle("request-status--success", !isError);
  requestStatusEl.hidden = false;
}

async function runExpansion(tabId) {
  const attempts = [];

  for (let attempt = 1; attempt <= 2; attempt += 1) {
    if (attempt > 1) {
      await chrome.scripting.executeScript({
        target: { tabId },
        func: () => {
          delete globalThis.__vibecheckExpand_strategies;
          delete globalThis.__vibecheckExpand_run;
        },
      });
    }

    const result = await runExpansionAttempt(tabId, attempt);
    attempts.push(result);

    if (result.status !== "failure" || !result.retryable) {
      const finalResult = {
        ...result,
        attempts,
        retried: attempts.length === 2,
      };
      logExpansionTelemetry(finalResult);
      return finalResult;
    }
  }

  const lastResult = attempts[attempts.length - 1];
  const finalResult = {
    ...lastResult,
    attempts,
    retried: true,
  };
  logExpansionTelemetry(finalResult);
  return finalResult;
}

async function runExpansionAttempt(tabId, attempt) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: EXPANSION_FILES,
    });

    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => globalThis.__vibecheckExpand_run(),
    });

    return normalizeExpandResult(result, attempt);
  } catch (error) {
    return {
      site: activeTab?.url ? new URL(activeTab.url).hostname : "unknown",
      iterations: 0,
      clicks: 0,
      useful_clicks: 0,
      scrolls: 0,
      duration_ms: 0,
      timed_out: false,
      error: error instanceof Error ? error.message : String(error),
      status: "failure",
      retryable: true,
      attempt,
    };
  }
}

function normalizeExpandResult(result, attempt) {
  if (!result || typeof result !== "object") {
    return {
      site: activeTab?.url ? new URL(activeTab.url).hostname : "unknown",
      iterations: 0,
      clicks: 0,
      useful_clicks: 0,
      scrolls: 0,
      duration_ms: 0,
      timed_out: false,
      error: "missing-result",
      status: "failure",
      retryable: true,
      attempt,
    };
  }

  return {
    site: result.site || (activeTab?.url ? new URL(activeTab.url).hostname : "unknown"),
    iterations: Number(result.iterations) || 0,
    clicks: Number(result.clicks) || 0,
    useful_clicks: Number(result.useful_clicks) || 0,
    scrolls: Number(result.scrolls) || 0,
    duration_ms: Number(result.duration_ms) || 0,
    timed_out: Boolean(result.timed_out),
    error: result.error || null,
    status: result.status || "failure",
    retryable: Boolean(result.retryable),
    attempt,
  };
}

function logExpansionTelemetry(result) {
  const attempts = Array.isArray(result.attempts) ? result.attempts.length : 1;
  console.log(JSON.stringify({
    event: "vibecheck.extension.expand_pass",
    site: result.site,
    enabled: true,
    iterations: result.iterations,
    clicks: result.clicks,
    scrolls: result.scrolls,
    useful_clicks: result.useful_clicks,
    duration_ms: result.duration_ms,
    timed_out: result.timed_out,
    attempts,
    retried: attempts === 2,
    retryable: result.retryable,
    error: result.error,
    status: result.status,
    ts: Date.now(),
  }));
}

function renderExpandStatus(result) {
  if (!result || result.status === "success" || result.status === "unsupported") {
    hideExpandStatus();
    return;
  }

  expandStatus.classList.toggle("error", result.status === "failure");
  expandStatus.textContent =
    result.status === "partial"
      ? "Expanding comments was partially successful"
      : "Expanding comments was not successful";
  expandStatus.hidden = false;
}

function hideExpandStatus() {
  expandStatus.hidden = true;
  expandStatus.classList.remove("error");
  expandStatus.textContent = "";
}

async function captureScreenshotForSubmission(tabId) {
  try {
    const screenshotBase64 = await captureFullPageScreenshot(tabId);
    if (!screenshotBase64) {
      return null;
    }
    if (screenshotBase64.length > MAX_SCREENSHOT_BASE64_LENGTH) {
      console.warn("[vibecheck] screenshot dropped because it exceeds 20MB");
      return null;
    }
    return screenshotBase64;
  } catch (error) {
    console.warn("[vibecheck] screenshot capture failed", error);
    return null;
  }
}

async function captureFullPageScreenshot(tabId) {
  const debuggee = { tabId };
  let attached = false;
  await chrome.debugger.attach(debuggee, "1.3");
  attached = true;
  try {
    const result = await chrome.debugger.sendCommand(
      debuggee,
      "Page.captureScreenshot",
      { format: "png", captureBeyondViewport: true }
    );
    return typeof result?.data === "string" ? result.data : null;
  } finally {
    if (attached) {
      try {
        await chrome.debugger.detach(debuggee);
      } catch (error) {
        console.warn("[vibecheck] debugger detach failed", error);
      }
    }
  }
}

async function capturePage(tabId) {
  const [injection] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const description =
        document.querySelector('meta[property="og:description"]')?.content ||
        document.querySelector('meta[name="description"]')?.content ||
        null;

      return {
        html: document.documentElement.outerHTML,
        title: document.title || null,
        description,
      };
    },
  });

  if (!injection?.result?.html) {
    throw new Error("Could not capture page HTML.");
  }

  return injection.result;
}

function buildScrapeUrl() {
  const url = new URL(`${BASE_URL}/api/scrape`);
  return url.toString();
}

function compactPayload(payload) {
  return Object.fromEntries(
    Object.entries(payload).filter(
      ([, value]) => value !== null && value !== undefined && value !== ""
    )
  );
}

async function readResponseBody(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function showSuccess(body) {
  const analyzeUrl = body.analyze_url || body.analyzeUrl;
  const jobId = body.job_id || body.jobId || body.id;

  resultSection.classList.remove("error");
  resultContent.replaceChildren();

  if (analyzeUrl) {
    const link = document.createElement("a");
    link.href = analyzeUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = analyzeUrl;
    resultContent.append(link);
  } else {
    resultContent.textContent = "Submitted successfully.";
  }

  if (jobId) {
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `Job ID: ${jobId}`;
    resultContent.append(meta);
  }

  resultSection.hidden = false;
  setStatus("Submitted.");
}

function showError(title, message) {
  resultSection.classList.add("error");
  resultContent.replaceChildren();

  const strong = document.createElement("strong");
  strong.textContent = title;
  resultContent.append(strong);

  const detail = document.createElement("div");
  detail.className = "meta";
  detail.textContent = message;
  resultContent.append(detail);

  resultSection.hidden = false;
  setStatus("Submission failed.");
}

function hideResult() {
  resultSection.hidden = true;
  resultContent.replaceChildren();
}

function setPhase(phase) {
  const isBusy = phase !== "idle";
  submitButton.disabled = isBusy;
  submitButton.textContent = phase === "expanding" ? "Expanding comments..." : isBusy ? "Submitting..." : "Submit";

  const statuses = {
    idle: "",
    expanding: "",
    capturing: "Capturing page HTML...",
    submitting: "Posting to endpoint...",
  };
  setStatus(statuses[phase] || "");
}

function setStatus(message) {
  statusEl.textContent = message;
}

function formatErrorBody(body) {
  if (typeof body === "string") {
    return body;
  }

  if (body?.detail) {
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  }

  if (body?.message) {
    return body.message;
  }

  return JSON.stringify(body);
}
