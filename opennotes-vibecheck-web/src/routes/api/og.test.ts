import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

vi.mock("~/lib/api-client.server", () => ({
  pollJob: vi.fn(),
}));

vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  return {
    ...actual,
    readFileSync: (path: string) => {
      return actual.readFileSync(path);
    },
  };
});

import { GET } from "./og";
import { pollJob } from "~/lib/api-client.server";

function buildEvent(search = ""): APIEvent {
  const url = `http://localhost:3000/api/og${search}`;
  const request = new Request(url, { method: "GET" });
  return {
    request,
    params: {},
    nativeEvent: {} as unknown,
    locals: {},
    response: {} as unknown,
    fetch: globalThis.fetch,
    clientAddress: null,
  } as unknown as APIEvent;
}

describe("GET /api/og", () => {
  beforeEach(() => {
    vi.mocked(pollJob).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("generic card: returns 200 with image/png content-type and non-empty body", async () => {
    const response = await GET(buildEvent());

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const buffer = await response.arrayBuffer();
    expect(buffer.byteLength).toBeGreaterThan(0);
  });

  it("generic card: uses terminal cache-control (immutable)", async () => {
    const response = await GET(buildEvent());

    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
  });

  it("nonexistent job: pollJob throws → falls back to generic card with terminal cache", async () => {
    vi.mocked(pollJob).mockRejectedValue(new Error("404 not found"));

    const response = await GET(buildEvent("?job=nonexistent-job-id"));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
    const buffer = await response.arrayBuffer();
    expect(buffer.byteLength).toBeGreaterThan(0);
  });

  it("terminal job state: returns 200 with terminal cache-control", async () => {
    vi.mocked(pollJob).mockResolvedValue({
      job_id: "test-job-123",
      status: "done",
      page_title: "Test Article Title",
      url: "https://example.com/article",
      sidebar_payload: {
        weather_report: {
          truth: { label: "sourced" },
          relevance: { label: "on_topic" },
          sentiment: { label: "positive" },
        },
        facts_claims: null,
        opinions_sentiments: null,
        safety: null,
        tone_dynamics: null,
      },
      error_code: null,
      sections: {},
    } as unknown as import("~/lib/api-client.server").JobState);

    const response = await GET(buildEvent("?job=test-job-123"));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
  });

  it("non-terminal job state: returns 200 with short cache-control", async () => {
    vi.mocked(pollJob).mockResolvedValue({
      job_id: "analyzing-job-456",
      status: "analyzing",
      page_title: null,
      url: null,
      sidebar_payload: null,
      error_code: null,
      sections: {},
    } as unknown as import("~/lib/api-client.server").JobState);

    const response = await GET(buildEvent("?job=analyzing-job-456"));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=300, s-maxage=300");
  });

  it("partial job state (terminal): returns terminal cache-control", async () => {
    vi.mocked(pollJob).mockResolvedValue({
      job_id: "partial-job-789",
      status: "partial",
      page_title: "Partial Result",
      url: "https://news.example.com/story",
      sidebar_payload: {
        weather_report: {
          truth: { label: "factual_claims" },
          relevance: { label: "insightful" },
          sentiment: { label: "neutral" },
        },
        facts_claims: null,
        opinions_sentiments: null,
        safety: null,
        tone_dynamics: null,
      },
      error_code: null,
      sections: {},
    } as unknown as import("~/lib/api-client.server").JobState);

    const response = await GET(buildEvent("?job=partial-job-789"));

    expect(response.status).toBe(200);
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
  });
});
