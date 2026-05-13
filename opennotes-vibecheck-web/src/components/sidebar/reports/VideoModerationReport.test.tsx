import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import VideoModerationReport from "./VideoModerationReport";

type VideoModerationMatch = components["schemas"]["VideoModerationMatch"];
type VideoSegmentFinding = components["schemas"]["VideoSegmentFinding"];

function videoMatch(
  overrides: Partial<VideoModerationMatch> = {},
): VideoModerationMatch {
  return {
    utterance_id: "u-video",
    video_url: "https://cdn.example.test/video.mp4",
    segment_findings: [],
    flagged: false,
    max_likelihood: 0,
    ...overrides,
  };
}

function segmentFinding(
  overrides: Partial<VideoSegmentFinding> = {},
): VideoSegmentFinding {
  return {
    start_offset_ms: 0,
    end_offset_ms: 1000,
    adult: 0,
    violence: 0,
    racy: 0,
    medical: 0,
    spoof: 0,
    flagged: false,
    max_likelihood: 0,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("VideoModerationReport", () => {
  it("shows an inconclusive analysis error when flagged with zero segments", () => {
    render(() => (
      <VideoModerationReport
        matches={[
          videoMatch({ flagged: true, max_likelihood: 1, segment_findings: [] }),
        ]}
      />
    ));

    expect(
      screen.getByTestId("video-moderation-no-segments-error"),
    ).toBeDefined();
    const el = screen.getByTestId("video-moderation-no-segments-error");
    expect(el.textContent).toContain("Analysis error:");
    expect(el.textContent).toContain("inconclusive");
    expect(el.textContent).not.toContain("video was flagged");
  });

  it("shows muted fallback text when non-flagged with zero segments", () => {
    render(() => (
      <VideoModerationReport
        matches={[videoMatch({ flagged: false, segment_findings: [] })]}
      />
    ));

    expect(
      screen.queryByTestId("video-moderation-no-segments-error"),
    ).toBeNull();
    const match = screen.getByTestId("video-moderation-match");
    expect(match.textContent).toContain("No video segments returned.");
  });

  it("renders segment findings list when flagged with non-empty segments", () => {
    render(() => (
      <VideoModerationReport
        matches={[
          videoMatch({
            flagged: true,
            segment_findings: [
              segmentFinding({ flagged: true, adult: 0.9, max_likelihood: 0.9 }),
            ],
          }),
        ]}
      />
    ));

    expect(
      screen.queryByTestId("video-moderation-no-segments-error"),
    ).toBeNull();
    expect(screen.getAllByTestId("video-frame-finding")).toHaveLength(1);
  });
});
