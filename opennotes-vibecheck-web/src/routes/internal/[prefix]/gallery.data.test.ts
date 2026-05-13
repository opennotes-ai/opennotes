import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { clientGetMock } = vi.hoisted(() => ({
  clientGetMock: vi.fn(),
}));

vi.mock("~/lib/api-client.server", async () => {
  const actual = await vi.importActual<typeof import("~/lib/api-client.server")>(
    "~/lib/api-client.server",
  );
  return { ...actual, getClient: () => ({ GET: clientGetMock }) };
});

describe("getInternalRecentAnalyses", () => {
  beforeEach(() => {
    clientGetMock.mockReset();
    vi.resetModules();
  });

  it("forwards prefix header and limit query to the internal endpoint", async () => {
    const fixture = [
      {
        job_id: "job-1",
        source_type: "pdf",
        source_url: "http://localhost/private",
        page_title: "Private Page",
        screenshot_url: null,
        preview_description: null,
        completed_at: "2026-01-01T00:00:00Z",
      },
    ];
    clientGetMock.mockResolvedValueOnce({ data: fixture, error: null });

    const { getInternalRecentAnalyses } = await import("./gallery.data");
    const result = await getInternalRecentAnalyses("private-prefix", 37);

    expect(result).toEqual(fixture);
    expect(clientGetMock).toHaveBeenCalledWith(
      "/api/internal/analyses/recent-unfiltered",
      {
        params: { query: { limit: 37 } },
        headers: { "X-Internal-Prefix": "private-prefix" },
      },
    );
  });

  it("surfaces backend 404 as a thrown 404 Response", async () => {
    clientGetMock.mockResolvedValueOnce({
      data: null,
      error: { detail: "Not Found" },
      response: new Response(null, { status: 404 }),
    });

    const { getInternalRecentAnalyses } = await import("./gallery.data");
    await expect(getInternalRecentAnalyses("wrong-prefix", 25)).rejects.toMatchObject({
      status: 404,
    });
  });

  it("returns [] for non-auth upstream errors without logging", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    clientGetMock.mockResolvedValueOnce({
      data: null,
      error: { error_code: "internal" },
      response: new Response(null, { status: 503 }),
    });

    const { getInternalRecentAnalyses } = await import("./gallery.data");
    const result = await getInternalRecentAnalyses("private-prefix", 25);

    expect(result).toEqual([]);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("returns [] for transport failures without logging", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    clientGetMock.mockRejectedValueOnce(new Error("network down"));

    const { getInternalRecentAnalyses } = await import("./gallery.data");
    const result = await getInternalRecentAnalyses("private-prefix", 25);

    expect(result).toEqual([]);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe("assertValidInternalPrefix", () => {
  const originalPrefix = process.env.VIBECHECK_PRIVATE_PATH_PREFIX;

  afterEach(() => {
    if (originalPrefix === undefined) {
      delete process.env.VIBECHECK_PRIVATE_PATH_PREFIX;
    } else {
      process.env.VIBECHECK_PRIVATE_PATH_PREFIX = originalPrefix;
    }
  });

  it("allows a matching server-only prefix", async () => {
    process.env.VIBECHECK_PRIVATE_PATH_PREFIX = "private-prefix";

    const { assertValidInternalPrefix } = await import("./gallery.data");

    await expect(assertValidInternalPrefix("private-prefix")).resolves.toBeUndefined();
  });

  it("throws 404 when the prefix is wrong", async () => {
    process.env.VIBECHECK_PRIVATE_PATH_PREFIX = "private-prefix";

    const { assertValidInternalPrefix } = await import("./gallery.data");

    await expect(assertValidInternalPrefix("wrong-prefix")).rejects.toMatchObject({
      status: 404,
    });
  });

  it("throws 404 when the env var is empty", async () => {
    delete process.env.VIBECHECK_PRIVATE_PATH_PREFIX;

    const { assertValidInternalPrefix } = await import("./gallery.data");

    await expect(assertValidInternalPrefix("anything")).rejects.toMatchObject({
      status: 404,
    });
  });
});
