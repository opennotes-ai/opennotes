#!/usr/bin/env python3
"""
Simplified Community Notes scoring demo for sample datasets.

This script demonstrates scoring calculations on sampled data without the full
Community Notes algorithm complexity that requires larger datasets.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


class SimplifiedScorer:
    """Simplified scoring algorithm for demonstration purposes."""

    def __init__(self):
        self.note_scores = {}
        self.user_scores = {}

    def calculate_note_scores(
        self, _notes_df: pd.DataFrame, ratings_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Calculate simplified note scores based on ratings."""
        # Group ratings by noteId
        note_groups = ratings_df.groupby("noteId")

        scored_notes = []
        for note_id, group in note_groups:
            helpful_count = group["helpful"].sum() if "helpful" in group.columns else 0
            total_ratings = len(group)

            # Simple scoring: helpful ratio with penalty for low engagement
            if total_ratings > 0:
                helpfulness_ratio = helpful_count / total_ratings
                engagement_factor = min(1.0, total_ratings / 10)  # Max out at 10 ratings
                score = helpfulness_ratio * engagement_factor
            else:
                score = 0.0

            # Determine status based on score and thresholds
            if score >= 0.6 and total_ratings >= 5:
                status = "CURRENTLY_RATED_HELPFUL"
            elif score <= 0.3 and total_ratings >= 3:
                status = "CURRENTLY_RATED_NOT_HELPFUL"
            else:
                status = "NEEDS_MORE_RATINGS"

            scored_notes.append(
                {
                    "noteId": note_id,
                    "coreNoteIntercept": score,
                    "currentStatus": status,
                    "numRatings": total_ratings,
                    "helpfulRatio": helpfulness_ratio if total_ratings > 0 else 0,
                }
            )

        return pd.DataFrame(scored_notes)

    def calculate_user_helpfulness(
        self, ratings_df: pd.DataFrame, scored_notes_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Calculate user helpfulness scores based on rating quality."""
        # Join ratings with scored notes
        ratings_with_scores = ratings_df.merge(
            scored_notes_df[["noteId", "currentStatus"]], on="noteId", how="left"
        )

        # Group by rater
        rater_groups = ratings_with_scores.groupby("raterParticipantId")

        user_scores = []
        for rater_id, group in rater_groups:
            total_ratings = len(group)

            # Count agreements with final status
            agreements = 0
            for _, rating in group.iterrows():
                if (
                    rating["currentStatus"] == "CURRENTLY_RATED_HELPFUL"
                    and rating.get("helpful", 0) == 1
                ) or (
                    rating["currentStatus"] == "CURRENTLY_RATED_NOT_HELPFUL"
                    and rating.get("notHelpful", 0) == 1
                ):
                    agreements += 1

            agreement_rate = agreements / total_ratings if total_ratings > 0 else 0

            user_scores.append(
                {
                    "raterParticipantId": rater_id,
                    "coreRaterIntercept": agreement_rate,
                    "numRatings": total_ratings,
                    "agreementRate": agreement_rate,
                }
            )

        return pd.DataFrame(user_scores)


def load_sample_data(sample_dir: Path) -> dict[str, pd.DataFrame]:
    """Load TSV files from sample directory."""
    data = {}

    # Load notes
    notes_file = sample_dir / "notes.tsv"
    if notes_file.exists():
        data["notes"] = pd.read_csv(notes_file, sep="\t")
        print(f"  Loaded {len(data['notes'])} notes")

    # Load ratings
    ratings_file = sample_dir / "ratings.tsv"
    if ratings_file.exists():
        data["ratings"] = pd.read_csv(ratings_file, sep="\t")
        print(f"  Loaded {len(data['ratings'])} ratings")

    # Load user enrollment
    enrollment_file = sample_dir / "userEnrollment.tsv"
    if enrollment_file.exists():
        data["userEnrollment"] = pd.read_csv(enrollment_file, sep="\t")
        print(f"  Loaded {len(data['userEnrollment'])} user enrollments")

    # Load note status history
    status_file = sample_dir / "noteStatusHistory.tsv"
    if status_file.exists():
        data["noteStatusHistory"] = pd.read_csv(status_file, sep="\t")
        print(f"  Loaded {len(data['noteStatusHistory'])} status history records")

    return data


def run_scoring_demo(sample_size: str, data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run simplified scoring demonstration."""
    print(f"\n{'=' * 60}")
    print(f"Running simplified scoring on {sample_size} sample")
    print(f"{'=' * 60}")

    sample_dir = data_dir / f"sample_{sample_size}"
    if not sample_dir.exists():
        raise FileNotFoundError(f"Sample directory not found: {sample_dir}")

    # Load data
    print(f"\nLoading data from {sample_dir}...")
    data = load_sample_data(sample_dir)

    if "notes" not in data or "ratings" not in data:
        raise ValueError("Missing required data files (notes.tsv and ratings.tsv)")

    # Initialize scorer
    scorer = SimplifiedScorer()

    # Track timing
    start_time = time.time()

    # Calculate note scores
    print("\nCalculating note scores...")
    scored_notes = scorer.calculate_note_scores(data["notes"], data["ratings"])
    print(f"  Scored {len(scored_notes)} notes")

    # Calculate user helpfulness
    print("\nCalculating user helpfulness scores...")
    user_scores = scorer.calculate_user_helpfulness(data["ratings"], scored_notes)
    print(f"  Scored {len(user_scores)} users")

    # Calculate statistics
    execution_time = time.time() - start_time

    # Status distribution
    status_dist = scored_notes["currentStatus"].value_counts().to_dict()
    print("\nNote status distribution:")
    for status, count in status_dist.items():
        print(f"  {status}: {count}")

    # Score statistics
    score_stats = {
        "mean": float(scored_notes["coreNoteIntercept"].mean()),
        "std": float(scored_notes["coreNoteIntercept"].std()),
        "min": float(scored_notes["coreNoteIntercept"].min()),
        "max": float(scored_notes["coreNoteIntercept"].max()),
    }

    print("\nScore statistics:")
    print(f"  Mean: {score_stats['mean']:.3f}")
    print(f"  Std:  {score_stats['std']:.3f}")
    print(f"  Min:  {score_stats['min']:.3f}")
    print(f"  Max:  {score_stats['max']:.3f}")

    # Save results
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save scored notes
    notes_output = output_dir / f"scored_notes_{sample_size}_{timestamp}.csv"
    scored_notes.to_csv(notes_output, index=False)
    print(f"\nSaved scored notes to: {notes_output}")

    # Save user scores
    users_output = output_dir / f"user_scores_{sample_size}_{timestamp}.csv"
    user_scores.to_csv(users_output, index=False)
    print(f"Saved user scores to: {users_output}")

    # Create summary
    summary = {
        "sample_size": sample_size,
        "timestamp": timestamp,
        "execution_time_seconds": round(execution_time, 2),
        "data_counts": {
            "notes": len(data["notes"]),
            "ratings": len(data["ratings"]),
            "users_enrolled": len(data.get("userEnrollment", [])),
        },
        "scoring_results": {
            "notes_scored": len(scored_notes),
            "users_scored": len(user_scores),
            "status_distribution": status_dist,
            "score_statistics": score_stats,
        },
        "performance": {
            "notes_per_second": round(len(scored_notes) / execution_time, 2),
            "ratings_per_second": round(len(data["ratings"]) / execution_time, 2),
        },
    }

    # Save summary
    summary_output = output_dir / f"scoring_summary_{sample_size}_{timestamp}.json"
    with summary_output.open("w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved summary to: {summary_output}")

    print(f"\n✓ Scoring completed in {execution_time:.2f} seconds")

    return summary


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run simplified Community Notes scoring demonstration"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "communitynotes_data" / "samples",
        help="Path to samples directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "scoring_results",
        help="Output directory for results",
    )
    parser.add_argument(
        "--sample-size",
        choices=["1k", "10k", "100k"],
        required=True,
        help="Sample size to process",
    )

    args = parser.parse_args()

    # Run scoring
    try:
        run_scoring_demo(args.sample_size, args.data_dir, args.output_dir)
        return 0
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
