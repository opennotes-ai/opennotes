import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { APIEvent } from "@solidjs/start/server";

vi.mock("~/lib/api-client.server", () => ({
  pollJob: vi.fn(),
}));

vi.mock("satori", () => ({
  default: vi.fn(),
}));


import { GET } from "./og";
import { pollJob } from "~/lib/api-client.server";
import satori from "satori";
import type { JobState } from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";

const FAKE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630"></svg>`;
type SidebarPayload = components["schemas"]["SidebarPayload"];

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

function makeJobState(overrides: Partial<JobState> & Pick<JobState, "job_id" | "status">): JobState {
  return {
    url: "https://example.com",
    attempt_id: "00000000-0000-0000-0000-000000000001",
    source_type: "url",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    sidebar_payload_complete: false,
    cached: false,
    next_poll_ms: 1500,
    utterance_count: 0,
    page_title: null,
    sidebar_payload: null,
    error_code: null,
    sections: {},
    ...overrides,
  } satisfies JobState;
}

function makeSidebarPayload(overrides: Partial<SidebarPayload> = {}): SidebarPayload {
  return {
    safety: { harmful_content_matches: [] },
    weather_report: {
      truth: { label: "sourced" },
      relevance: { label: "on_topic" },
      sentiment: { label: "neutral" },
    },
    ...overrides,
  } as SidebarPayload;
}

function renderedTreeText(): string {
  return JSON.stringify(vi.mocked(satori).mock.calls.at(-1)?.[0]);
}

function renderedTextIndex(value: string): number {
  return renderedTreeText().indexOf(`"${value}"`);
}

describe("GET /api/og", () => {
  beforeEach(() => {
    vi.mocked(pollJob).mockReset();
    vi.mocked(satori).mockResolvedValue(FAKE_SVG);
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
    vi.mocked(pollJob).mockResolvedValue(
      makeJobState({
        job_id: "test-job-123",
        status: "done",
        page_title: "Test Article Title",
        url: "https://example.com/article",
        sidebar_payload_complete: true,
      }),
    );

    const response = await GET(buildEvent("?job=test-job-123"));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
  });

  it("non-terminal job state: returns 200 with short cache-control", async () => {
    vi.mocked(pollJob).mockResolvedValue(
      makeJobState({
        job_id: "analyzing-job-456",
        status: "analyzing",
        page_title: null,
        url: "https://example.com",
        sidebar_payload: null,
      }),
    );

    const response = await GET(buildEvent("?job=analyzing-job-456"));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=300, s-maxage=300");
  });

  it("partial job state (terminal): returns terminal cache-control", async () => {
    vi.mocked(pollJob).mockResolvedValue(
      makeJobState({
        job_id: "partial-job-789",
        status: "partial",
        page_title: "Partial Result",
        url: "https://news.example.com/story",
        sidebar_payload_complete: true,
      }),
    );

    const response = await GET(buildEvent("?job=partial-job-789"));

    expect(response.status).toBe(200);
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
  });

  it("unknown status string: yields terminal cache-control (regression for status inversion)", async () => {
    vi.mocked(pollJob).mockResolvedValue(
      makeJobState({
        job_id: "foobar-job-999",
        status: "foobar" as JobState["status"],
      }),
    );

    const response = await GET(buildEvent("?job=foobar-job-999"));

    expect(response.status).toBe(200);
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
  });

  it("renderCard throws: response is still 200 + image/png + terminal cache", async () => {
    vi.mocked(satori).mockRejectedValue(new Error("Satori: missing glyph"));

    const response = await GET(buildEvent());

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    const cc = response.headers.get("cache-control");
    expect(cc).toBe("public, max-age=43200, s-maxage=43200, immutable");
    const buffer = await response.arrayBuffer();
    expect(buffer.byteLength).toBeGreaterThan(0);
  });

  it("job card: includes formatted Safety recommendation in the right column", async () => {
    vi.mocked(pollJob).mockResolvedValue(
      makeJobState({
        job_id: "safe-job-001",
        status: "done",
        page_title: "Safe Article",
        sidebar_payload_complete: true,
        sidebar_payload: makeSidebarPayload({
          safety: {
            harmful_content_matches: [],
            recommendation: {
              level: "safe",
              rationale: "No verified harmful content signals.",
            },
          },
        }),
      }),
    );

    const response = await GET(buildEvent("?job=safe-job-001"));

    expect(response.status).toBe(200);
    expect(pollJob).toHaveBeenCalledWith("safe-job-001", expect.any(Object));
    expect(renderedTreeText()).toContain('"Safety"');
    expect(renderedTreeText()).toContain('"Safe"');
    expect(renderedTreeText()).toContain('"Truth"');
    expect(renderedTreeText()).toContain('"Sourced"');
    expect(renderedTreeText()).toContain('"Relevance"');
    expect(renderedTreeText()).toContain('"On Topic"');
    expect(renderedTreeText()).toContain('"Sentiment"');
    expect(renderedTreeText()).toContain('"Neutral"');
    expect(renderedTextIndex("Safety")).toBeLessThan(renderedTextIndex("Truth"));
    expect(renderedTextIndex("Truth")).toBeLessThan(renderedTextIndex("Relevance"));
    expect(renderedTextIndex("Relevance")).toBeLessThan(renderedTextIndex("Sentiment"));
  });

  it("job card: includes Safety fallback when recommendation is missing", async () => {
    vi.mocked(pollJob).mockResolvedValue(
      makeJobState({
        job_id: "missing-safety-job-002",
        status: "done",
        page_title: "Incomplete Safety Article",
        sidebar_payload_complete: true,
        sidebar_payload: makeSidebarPayload({
          safety: { harmful_content_matches: [] },
        }),
      }),
    );

    const response = await GET(buildEvent("?job=missing-safety-job-002"));

    expect(response.status).toBe(200);
    expect(pollJob).toHaveBeenCalledWith("missing-safety-job-002", expect.any(Object));
    expect(renderedTreeText()).toContain('"Safety"');
    expect(renderedTreeText()).toContain('"—"');
  });
});
