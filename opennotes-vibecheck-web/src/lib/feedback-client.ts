import type { components } from "./generated-types";

type OpenReq = components["schemas"]["FeedbackOpenRequest"];
type OpenRes = components["schemas"]["FeedbackOpenResponse"];
type SubmitReq = components["schemas"]["FeedbackSubmitRequest"];
type CombinedReq = components["schemas"]["FeedbackCombinedRequest"];

export type OpenInput = Omit<OpenReq, "kind">;
export type CombinedInput = Omit<CombinedReq, "kind">;

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

async function safeFetch(
  input: RequestInfo | URL,
  init: RequestInit,
): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    if (error instanceof FeedbackApiError) throw error;
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new FeedbackApiError(0, null, message);
  }
}

export async function openFeedback(payload: OpenInput): Promise<OpenRes> {
  const body: OpenReq = { ...payload, kind: "open" };
  const response = await safeFetch("/api/feedback", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await handleResponse(response)) as OpenRes;
}

export async function submitFeedback(
  id: string,
  payload: SubmitReq,
): Promise<void> {
  const response = await safeFetch(`/api/feedback/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await handleResponse(response);
}

export async function submitFeedbackCombined(
  payload: CombinedInput,
): Promise<OpenRes> {
  const body: CombinedReq = { ...payload, kind: "combined" };
  const response = await safeFetch("/api/feedback", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await handleResponse(response)) as OpenRes;
}
