const STORAGE_KEYS = {
  endpointUrl: "vibecheck_endpoint_url",
  apiKey: "vibecheck_api_key",
};

const endpointInput = document.querySelector("#endpoint-url");
const apiKeyInput = document.querySelector("#api-key");
const currentUrlInput = document.querySelector("#current-url");
const submitButton = document.querySelector("#submit-btn");
const statusEl = document.querySelector("#status");
const resultSection = document.querySelector("#result");
const resultContent = document.querySelector("#result-content");

let activeTab = null;

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  await loadActiveTab();
});

endpointInput.addEventListener("change", saveSettings);
endpointInput.addEventListener("blur", saveSettings);
apiKeyInput.addEventListener("change", saveSettings);
apiKeyInput.addEventListener("blur", saveSettings);
submitButton.addEventListener("click", submitCurrentPage);

async function loadSettings() {
  const settings = await chrome.storage.sync.get([
    STORAGE_KEYS.endpointUrl,
    STORAGE_KEYS.apiKey,
  ]);

  endpointInput.value = settings[STORAGE_KEYS.endpointUrl] || "";
  apiKeyInput.value = settings[STORAGE_KEYS.apiKey] || "";
}

async function saveSettings() {
  await chrome.storage.sync.set({
    [STORAGE_KEYS.endpointUrl]: endpointInput.value.trim(),
    [STORAGE_KEYS.apiKey]: apiKeyInput.value.trim(),
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
  hideResult();
  await saveSettings();

  const endpointUrl = endpointInput.value.trim();
  const apiKey = apiKeyInput.value.trim();

  if (!endpointUrl) {
    showError("Missing endpoint URL", "Configure the Vibecheck endpoint URL in settings.");
    return;
  }

  if (!apiKey) {
    showError("Missing API key", "Configure the API key in settings.");
    return;
  }

  if (!activeTab?.id || !activeTab?.url) {
    showError("No active page", "Open a browser tab before submitting.");
    return;
  }

  setSubmitting(true);

  try {
    const page = await capturePage(activeTab.id);
    const response = await fetch(buildScrapeUrl(endpointUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(compactPayload({
        url: activeTab.url,
        source_url: activeTab.url,
        html: page.html,
        title: page.title,
        description: page.description,
      })),
    });

    const responseBody = await readResponseBody(response);

    if (!response.ok) {
      showError(`HTTP ${response.status}`, formatErrorBody(responseBody));
      return;
    }

    showSuccess(responseBody);
  } catch (error) {
    showError("Network error", error instanceof Error ? error.message : String(error));
  } finally {
    setSubmitting(false);
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

function buildScrapeUrl(input) {
  const url = new URL(input);
  const normalizedPath = url.pathname.replace(/\/+$/, "");

  if (normalizedPath.endsWith("/api/scrape")) {
    return url.toString();
  }

  url.pathname = `${normalizedPath}/api/scrape`.replace(/^\/?/, "/");
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

function setSubmitting(isSubmitting) {
  submitButton.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "Submitting..." : "Submit";
  setStatus(isSubmitting ? "Capturing page HTML..." : "");
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
