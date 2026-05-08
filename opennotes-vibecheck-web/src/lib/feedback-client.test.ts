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
  it("resolves with parsed { id } on 201", async () => {
    const fetchSpy = mockFetch(
      new Response(JSON.stringify({ id: FEEDBACK_ID }), { status: 201 }),
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
    expect(JSON.parse(init.body as string)).toEqual({
      ...OPEN_REQ,
      kind: "open",
    });
  });

  it("also accepts a 200 response (any 2xx)", async () => {
    mockFetch(
      new Response(JSON.stringify({ id: FEEDBACK_ID }), { status: 200 }),
    );

    const result = await openFeedback(OPEN_REQ);
    expect(result).toEqual({ id: FEEDBACK_ID });
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

  it("wraps network-layer fetch rejection as FeedbackApiError(status=0)", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    let caught: unknown;
    try {
      await openFeedback(OPEN_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(0);
    expect((caught as FeedbackApiError).message).toContain("Failed to fetch");
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

  it("wraps fetch network rejection as FeedbackApiError(status=0)", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    let caught: unknown;
    try {
      await submitFeedback(FEEDBACK_ID, SUBMIT_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(0);
  });
});

describe("submitFeedbackCombined", () => {
  it("POSTs to /api/feedback with combined payload (kind=combined) and resolves { id }", async () => {
    const fetchSpy = mockFetch(
      new Response(JSON.stringify({ id: FEEDBACK_ID }), { status: 201 }),
    );

    const result = await submitFeedbackCombined(COMBINED_REQ);

    expect(result).toEqual({ id: FEEDBACK_ID });

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/feedback");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual({
      ...COMBINED_REQ,
      kind: "combined",
    });
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

  it("wraps fetch network rejection as FeedbackApiError(status=0)", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    let caught: unknown;
    try {
      await submitFeedbackCombined(COMBINED_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(0);
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

describe("submitFeedback — 204 / empty-body branch", () => {
  it("treats a 204 response (no body) as success and resolves void without throwing JSON parse errors", async () => {
    mockFetch(new Response(null, { status: 204 }));

    await expect(
      submitFeedback(FEEDBACK_ID, SUBMIT_REQ),
    ).resolves.toBeUndefined();
  });

  it("treats a 200 response with empty body string as success", async () => {
    mockFetch(new Response("", { status: 200 }));

    await expect(
      submitFeedback(FEEDBACK_ID, SUBMIT_REQ),
    ).resolves.toBeUndefined();
  });

  it("does not throw when 204 body is empty (handleResponse returns null body)", async () => {
    mockFetch(new Response(null, { status: 204 }));

    let thrown: unknown = undefined;
    try {
      await submitFeedback(FEEDBACK_ID, SUBMIT_REQ);
    } catch (err) {
      thrown = err;
    }
    expect(thrown).toBeUndefined();
  });
});

describe("feedback-client — 4xx vs 5xx wrapping", () => {
  it.each([
    { status: 400, body: { detail: "bad request" } },
    { status: 401, body: { detail: "unauthorized" } },
    { status: 403, body: { detail: "forbidden" } },
    { status: 404, body: { detail: "not found" } },
    { status: 409, body: { detail: "conflict" } },
    { status: 422, body: { detail: [{ msg: "field required" }] } },
    { status: 429, body: { detail: "rate limited" } },
  ])(
    "wraps 4xx ($status) from openFeedback as FeedbackApiError preserving status and body",
    async ({ status, body }) => {
      mockFetch(new Response(JSON.stringify(body), { status }));

      let caught: unknown;
      try {
        await openFeedback(OPEN_REQ);
      } catch (err) {
        caught = err;
      }

      expect(caught).toBeInstanceOf(FeedbackApiError);
      const apiErr = caught as FeedbackApiError;
      expect(apiErr.status).toBe(status);
      expect(apiErr.status).toBeGreaterThanOrEqual(400);
      expect(apiErr.status).toBeLessThan(500);
      expect(apiErr.body).toEqual(body);
    },
  );

  it.each([
    { status: 500, body: { detail: "internal server error" } },
    { status: 502, body: { detail: "bad gateway" } },
    { status: 503, body: { detail: "service unavailable" } },
    { status: 504, body: { detail: "gateway timeout" } },
  ])(
    "wraps 5xx ($status) from openFeedback as FeedbackApiError preserving status and body",
    async ({ status, body }) => {
      mockFetch(new Response(JSON.stringify(body), { status }));

      let caught: unknown;
      try {
        await openFeedback(OPEN_REQ);
      } catch (err) {
        caught = err;
      }

      expect(caught).toBeInstanceOf(FeedbackApiError);
      const apiErr = caught as FeedbackApiError;
      expect(apiErr.status).toBe(status);
      expect(apiErr.status).toBeGreaterThanOrEqual(500);
      expect(apiErr.body).toEqual(body);
    },
  );

  it("wraps 4xx from submitFeedback (PATCH) preserving status and body", async () => {
    const body = { detail: "validation failed" };
    mockFetch(new Response(JSON.stringify(body), { status: 422 }));

    let caught: unknown;
    try {
      await submitFeedback(FEEDBACK_ID, SUBMIT_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(422);
    expect((caught as FeedbackApiError).body).toEqual(body);
  });

  it("wraps 5xx from submitFeedback (PATCH) preserving status and body", async () => {
    const body = { detail: "internal" };
    mockFetch(new Response(JSON.stringify(body), { status: 503 }));

    let caught: unknown;
    try {
      await submitFeedback(FEEDBACK_ID, SUBMIT_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(503);
    expect((caught as FeedbackApiError).body).toEqual(body);
  });

  it("falls back to plain-text body when error response is not JSON (4xx)", async () => {
    mockFetch(
      new Response("plain text error", {
        status: 418,
        headers: { "content-type": "text/plain" },
      }),
    );

    let caught: unknown;
    try {
      await openFeedback(OPEN_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    const apiErr = caught as FeedbackApiError;
    expect(apiErr.status).toBe(418);
    expect(apiErr.body).toBe("plain text error");
  });

  it("error body is null when 5xx response has no body at all", async () => {
    mockFetch(new Response(null, { status: 500 }));

    let caught: unknown;
    try {
      await openFeedback(OPEN_REQ);
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(FeedbackApiError);
    expect((caught as FeedbackApiError).status).toBe(500);
    expect((caught as FeedbackApiError).body).toBeNull();
  });
});
