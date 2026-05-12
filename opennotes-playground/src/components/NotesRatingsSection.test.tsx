import { describe, it, expect, vi } from "vitest";
import { render } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import NotesRatingsSection from "./NotesRatingsSection";

vi.mock("@opennotes/ui/components/ui/echart", () => ({
  EChart: (props: {
    option: {
      grid?: { left?: number; right?: number; top?: number; bottom?: number };
      yAxis?: { axisLabel?: { show?: boolean }; axisTick?: { show?: boolean }; axisLine?: { show?: boolean } };
    };
  }) => (
    <div
      data-testid="echart"
      data-grid={JSON.stringify(props.option.grid)}
      data-y-axis={JSON.stringify(props.option.yAxis)}
    />
  ),
}));

type NoteQualityData = components["schemas"]["NoteQualityData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];
type TimelineBucketData = components["schemas"]["TimelineBucketData"];

const noteQuality: NoteQualityData = {
  avg_helpfulness_score: 0.7,
  notes_by_status: {
    currently_rated_helpful: 1,
    needs_more_ratings: 1,
  },
  notes_by_classification: {
    helpful: 1,
    not_helpful: 1,
  },
};

const ratingDistribution: RatingDistributionData = {
  total_ratings: 105,
  overall: {
    helpful: 100,
    not_helpful: 5,
  },
  per_agent: [],
};

const buckets: TimelineBucketData[] = [
  {
    timestamp: "2026-01-01T00:00:00Z",
    notes_by_status: {
      currently_rated_helpful: 1,
      needs_more_ratings: 0,
    },
    ratings_by_level: {
      helpful: 99,
      not_helpful: 1,
    },
  },
  {
    timestamp: "2026-01-01T01:00:00Z",
    notes_by_status: {
      currently_rated_helpful: 1,
      needs_more_ratings: 1,
    },
    ratings_by_level: {
      helpful: 1,
      not_helpful: 4,
    },
  },
];

describe("NotesRatingsSection", () => {
  it("renders cumulative timelines with aligned plot grids", () => {
    const { getAllByTestId } = render(() => (
      <NotesRatingsSection
        noteQuality={noteQuality}
        ratingDistribution={ratingDistribution}
        buckets={buckets}
      />
    ));

    const [, cumulativeNotesChart, cumulativeRatingsChart] = getAllByTestId("echart");

    expect(cumulativeNotesChart?.getAttribute("data-grid")).toBe(
      JSON.stringify({ left: 10, right: 20, top: 30, bottom: 40 }),
    );
    expect(cumulativeRatingsChart?.getAttribute("data-grid")).toBe(
      JSON.stringify({ left: 10, right: 20, top: 30, bottom: 40 }),
    );
    expect(cumulativeNotesChart?.getAttribute("data-y-axis")).toBe(
      JSON.stringify({
        type: "value",
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
      }),
    );
    expect(cumulativeRatingsChart?.getAttribute("data-y-axis")).toBe(
      JSON.stringify({
        type: "value",
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
      }),
    );
  });
});
