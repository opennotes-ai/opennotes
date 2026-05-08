import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  openFeedback,
  submitFeedback,
  submitFeedbackCombined,
  FeedbackApiError,
} from "./feedback-client";

const OPEN_REQ = {
  page_path: "/analyze",
  user_agent: "Mozilla/5.0",
  referrer: "",
  bell_location: "sidebar",
  initial_type: "thumbs_up" as const,
};

const SUBMIT_REQ = {
  final_type: "thumbs_up" as const,
  email: "user@example.com",
  message: null,
};

const COMBINED_REQ = {
  page_path: "/analyze",
  user_agent: "Mozilla/5.0",
  referrer: "",
  bell_location: "sidebar",
  initial_type: "thumbs_down" as const,
  final_type: "thumbs_down" as const,
  email: null,
  message: "Nice analysis",
};

const FEEDBACK_ID = "11111111-2222-3333-4444-555555555555";

function mockFetch(response: Response) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("openFeedback", () => {
  it("resolves with parsed { id } on 200", async () => {
    const fetchSpy = mockFetch(
      new Response(JSON.stringify({ id: FEEDBACK_ID }), { status: 200 }),
    );

    const result = await openFeedback(OPEN_REQ);

    expect(result).toEqual({ id: FEEDBACK_ID });
    expect(fetchSpy).toHaveBeenCalledOnce();

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/feedback");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(JSON.parse(init.body as string)).toEqual(OPEN_REQ);
  });

  it("rejects with FeedbackApiError on 500", async () => {
    const errorBody = { detail: "Internal server error" };
    mockFetch(
      new Response(JSON.stringify(errorBody), { status: 500 }),
    );

    let caught: unknown;
    try {
      await openFeedback(OPEN_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    const apiErr = caught as FeedbackApiError;
    expect(apiErr.status).toBe(500);
    expect(apiErr.body).toEqual(errorBody);
  });

  it("rejects with FeedbackApiError on 422 with the parsed body", async () => {
    const errorBody = { detail: [{ msg: "field required" }] };
    mockFetch(
      new Response(JSON.stringify(errorBody), { status: 422 }),
    );

    let caught: unknown;
    try {
      await openFeedback(OPEN_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(422);
    expect((caught as FeedbackApiError).body).toEqual(errorBody);
  });
});

describe("submitFeedback", () => {
  it("resolves void on 204 (no body)", async () => {
    const fetchSpy = mockFetch(new Response(null, { status: 204 }));

    await expect(
      submitFeedback(FEEDBACK_ID, SUBMIT_REQ),
    ).resolves.toBeUndefined();

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/feedback/${FEEDBACK_ID}`);
    expect(init.method).toBe("PATCH");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(JSON.parse(init.body as string)).toEqual(SUBMIT_REQ);
  });

  it("resolves void on 200 (body present but not needed)", async () => {
    mockFetch(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await expect(
      submitFeedback(FEEDBACK_ID, SUBMIT_REQ),
    ).resolves.toBeUndefined();
  });

  it("rejects with FeedbackApiError with status 404 on not-found", async () => {
    const errorBody = { detail: "Not found" };
    mockFetch(
      new Response(JSON.stringify(errorBody), { status: 404 }),
    );

    let caught: unknown;
    try {
      await submitFeedback(FEEDBACK_ID, SUBMIT_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(404);
    expect((caught as FeedbackApiError).body).toEqual(errorBody);
  });
});

describe("submitFeedbackCombined", () => {
  it("POSTs to /api/feedback with combined payload and resolves { id }", async () => {
    const fetchSpy = mockFetch(
      new Response(JSON.stringify({ id: FEEDBACK_ID }), { status: 200 }),
    );

    const result = await submitFeedbackCombined(COMBINED_REQ);

    expect(result).toEqual({ id: FEEDBACK_ID });

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/feedback");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual(COMBINED_REQ);
  });

  it("rejects with FeedbackApiError on non-2xx", async () => {
    const errorBody = { detail: "Service unavailable" };
    mockFetch(
      new Response(JSON.stringify(errorBody), { status: 503 }),
    );

    let caught: unknown;
    try {
      await submitFeedbackCombined(COMBINED_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(503);
    expect((caught as FeedbackApiError).body).toEqual(errorBody);
  });
});

describe("FeedbackApiError", () => {
  it("exposes status and body on the error instance", () => {
    const err = new FeedbackApiError(400, { detail: "bad request" });
    expect(err.status).toBe(400);
    expect(err.body).toEqual({ detail: "bad request" });
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("FeedbackApiError");
  });

  it("uses provided message when given", () => {
    const err = new FeedbackApiError(500, null, "custom message");
    expect(err.message).toBe("custom message");
  });

  it("generates a default message from status when no message provided", () => {
    const err = new FeedbackApiError(422, null);
    expect(err.message).toContain("422");
  });
});
