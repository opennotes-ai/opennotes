import type { components } from "./generated-types";

type OpenReq = components["schemas"]["FeedbackOpenRequest"];
type OpenRes = components["schemas"]["FeedbackOpenResponse"];
type SubmitReq = components["schemas"]["FeedbackSubmitRequest"];
type CombinedReq = components["schemas"]["FeedbackCombinedRequest"];

export class FeedbackApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message?: string,
  ) {
    super(message ?? `Feedback API error (${status})`);
    this.name = "FeedbackApiError";
  }
}

async function handleResponse(response: Response): Promise<unknown> {
  let body: unknown;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  } else {
    body = null;
  }
  if (!response.ok) {
    throw new FeedbackApiError(response.status, body);
  }
  return body;
}

export async function openFeedback(payload: OpenReq): Promise<OpenRes> {
  const response = await fetch("/api/feedback", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await handleResponse(response)) as OpenRes;
}

export async function submitFeedback(
  id: string,
  payload: SubmitReq,
): Promise<void> {
  const response = await fetch(`/api/feedback/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await handleResponse(response);
}

export async function submitFeedbackCombined(
  payload: CombinedReq,
): Promise<OpenRes> {
  const response = await fetch("/api/feedback", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await handleResponse(response)) as OpenRes;
}
