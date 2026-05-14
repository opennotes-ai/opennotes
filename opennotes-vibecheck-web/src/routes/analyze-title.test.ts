import { describe, expect, it } from "vitest";
import type { JobState } from "~/lib/api-client.server";
import {
  analyzedTitleSource,
  formatAnalyzeDocumentTitle,
  lifecycleLabelForJob,
  truncateAnalyzeTitleSegment,
} from "./analyze-title";

function makeJobState(overrides: Partial<JobState> = {}): JobState {
  return {
    job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    url: "https://news.example.com/a",
    status: "analyzing",
    attempt_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    source_type: "url",
    created_at: "2026-05-14T00:00:00Z",
    updated_at: "2026-05-14T00:00:00Z",
    sidebar_payload_complete: false,
    cached: false,
    next_poll_ms: 1500,
    utterance_count: 0,
    ...overrides,
  } as JobState;
}

describe("analyze document title helpers", () => {
  it.each([
    ["Converting images to PDF", "extracting"],
    ["Extracting page content", "extracting"],
    ["Saving page content", "extracting"],
    ["Preparing analysis", "analyzing"],
    ["Running section analyses", "analyzing"],
    ["Computing safety guidance", "recommending"],
    ["Writing summary", "recommending"],
    ["Writing weather report", "recommending"],
    ["Writing overall recommendation", "recommending"],
    ["Finalizing results", "recommending"],
    ["Running analysis", "analyzing"],
  ] as const)(
    "maps backend activity label %s to %s",
    (activityLabel, expectedLifecycle) => {
      expect(
        lifecycleLabelForJob(
          makeJobState({
            status: "analyzing",
            activity_label: activityLabel,
          }),
        ),
      ).toBe(expectedLifecycle);
    },
  );

  it("derives lifecycle from status when activity label is missing", () => {
    expect(
      lifecycleLabelForJob(
        makeJobState({ status: "extracting", activity_label: null }),
      ),
    ).toBe("extracting");
    expect(
      lifecycleLabelForJob(
        makeJobState({ status: "analyzing", activity_label: null }),
      ),
    ).toBe("analyzing");
    expect(lifecycleLabelForJob(null)).toBe("analyzing");
  });

  it("formats terminal pass and flag decisions with analyzed title", () => {
    expect(
      formatAnalyzeDocumentTitle({
        job: makeJobState({
          status: "done",
          page_title: "Investigative feature",
        }),
        overallDecision: { verdict: "pass", reason: "No concerns" },
      }),
    ).toBe("vibecheck - ok - Investigative feature");
    expect(
      formatAnalyzeDocumentTitle({
        job: makeJobState({
          status: "done",
          page_title: "Heated comment thread",
        }),
        overallDecision: { verdict: "flag", reason: "Moderator review" },
      }),
    ).toBe("vibecheck - flagged - Heated comment thread");
  });

  it("formats terminal fallback labels when no decision is available", () => {
    expect(
      formatAnalyzeDocumentTitle({
        job: makeJobState({
          status: "partial",
          page_title: "Partially complete report",
        }),
        overallDecision: null,
      }),
    ).toBe("vibecheck - partial analysis - Partially complete report");
    expect(
      formatAnalyzeDocumentTitle({
        job: makeJobState({
          status: "failed",
          page_title: null,
          url: "https://news.example.com/failure",
        }),
        overallDecision: null,
      }),
    ).toBe("vibecheck - failed analysis - https://news.example.com/failure");
  });

  it("prefers trimmed page title before URL fallback", () => {
    expect(
      analyzedTitleSource({
        pageTitle: "  Article title  ",
        url: "https://news.example.com/a",
      }),
    ).toBe("Article title");
    expect(
      analyzedTitleSource({
        pageTitle: "   ",
        url: "https://news.example.com/a",
      }),
    ).toBe("https://news.example.com/a");
    expect(analyzedTitleSource({ pageTitle: null, url: null })).toBe(
      "Untitled analysis",
    );
  });

  it("truncates only the analyzed title segment around 100 characters", () => {
    const longTitle =
      "This title is intentionally long enough to exceed the browser title segment cap while keeping the prefix readable";
    expect(truncateAnalyzeTitleSegment(longTitle)).toBe(
      "This title is intentionally long enough to exceed the browser title segment cap while keeping the...",
    );
    expect(
      formatAnalyzeDocumentTitle({
        job: makeJobState({ status: "done", page_title: longTitle }),
        overallDecision: { verdict: "pass", reason: "No concerns" },
      }),
    ).toBe(
      "vibecheck - ok - This title is intentionally long enough to exceed the browser title segment cap while keeping the...",
    );
  });

  it("formats null job as generic analyzing without em dash", () => {
    const title = formatAnalyzeDocumentTitle({
      job: null,
      overallDecision: null,
    });

    expect(title).toBe("vibecheck - analyzing");
    expect(title).not.toMatch(/—/);
  });
});
