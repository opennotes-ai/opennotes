import type { components } from "~/lib/generated-types";

type NoteQualityData = components["schemas"]["NoteQualityData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];
type TimelineBucketData = components["schemas"]["TimelineBucketData"];

export default function NotesRatingsSection(props: {
  noteQuality: NoteQualityData;
  ratingDistribution: RatingDistributionData;
  buckets?: TimelineBucketData[];
  totalNotes?: number;
  totalRatings?: number;
}) {
  return (
    <section id="notes-ratings">
      <h2 class="mb-4 text-xl font-semibold">Notes & Ratings</h2>
      <p class="text-sm text-muted-foreground">
        Notes quality and rating distribution overview
      </p>
    </section>
  );
}
