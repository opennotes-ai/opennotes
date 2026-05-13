import type { components } from "~/lib/generated-types";

type VideoSegmentFinding = components["schemas"]["VideoSegmentFinding"];
type VideoModerationMatch = components["schemas"]["VideoModerationMatch"];
type LegacyVideoModerationMatch = Omit<
  VideoModerationMatch,
  "segment_findings"
> & {
  segment_findings?: VideoSegmentFinding[];
  frame_findings?: VideoSegmentFinding[];
};

const VERIFIED_VIDEO_THRESHOLD = 0.75;

export function segmentFindings(
  match: VideoModerationMatch,
): VideoSegmentFinding[] {
  const legacyMatch = match as LegacyVideoModerationMatch;
  if (Array.isArray(legacyMatch.segment_findings)) {
    return legacyMatch.segment_findings;
  }
  if (Array.isArray(legacyMatch.frame_findings)) {
    return legacyMatch.frame_findings;
  }
  return [];
}

export function isInconclusiveVideoMatch(match: VideoModerationMatch): boolean {
  return (
    match.flagged === true &&
    match.max_likelihood === 1 &&
    segmentFindings(match).length === 0
  );
}

export function hasVerifiedVideoFinding(match: VideoModerationMatch): boolean {
  return segmentFindings(match).some(
    (finding) =>
      finding.flagged === true ||
      finding.max_likelihood >= VERIFIED_VIDEO_THRESHOLD,
  );
}
