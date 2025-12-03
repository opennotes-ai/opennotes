#!/usr/bin/env python3
"""
Run Community Notes scoring algorithm on sampled datasets.

This script processes sampled Community Notes datasets through the scoring algorithm,
generating note scores, user helpfulness scores, and performance metrics for validation
and analysis.

Usage:
    uv run python scripts/run_community_notes_scoring.py --sample-size 1k
    uv run python scripts/run_community_notes_scoring.py --sample-size 10k --compare-original
    uv run python scripts/run_community_notes_scoring.py --all-samples --output-format json
"""

import argparse
import json
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

# Add the Community Notes scoring module to the path
CN_SCORING_PATH = Path(__file__).parent.parent.parent / "communitynotes" / "scoring" / "src"
sys.path.insert(0, str(CN_SCORING_PATH))

try:
    from scoring.pandas_utils import patch_pandas  # noqa: F401
    from scoring.process_data import LocalDataLoader  # noqa: F401
    from scoring.runner import _run_scorer
    from scoring.runner import parse_args as cn_parse_args  # noqa: F401
except ImportError as e:
    print(f"Error importing Community Notes scoring modules: {e}")
    print(f"Make sure the Community Notes repository is available at: {CN_SCORING_PATH}")
    sys.exit(1)


class PerformanceMetrics:
    """Track and report performance metrics for scoring runs."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.start_memory = None
        self.peak_memory = None
        self.notes_processed = 0
        self.ratings_processed = 0

    def start_tracking(self):
        """Start tracking performance metrics."""
        self.start_time = time.time()
        tracemalloc.start()
        self.start_memory = self._get_memory_usage()

    def stop_tracking(self):
        """Stop tracking and calculate final metrics."""
        self.end_time = time.time()
        _current, peak = tracemalloc.get_traced_memory()
        self.peak_memory = peak / (1024 * 1024)  # Convert to MB
        tracemalloc.stop()

    def _get_memory_usage(self):
        """Get current memory usage in MB."""
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)

    def get_execution_time(self):
        """Get total execution time in seconds."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0

    def get_throughput(self):
        """Calculate throughput (notes per second)."""
        exec_time = self.get_execution_time()
        if exec_time > 0:
            return self.notes_processed / exec_time
        return 0

    def to_dict(self):
        """Export metrics as dictionary."""
        return {
            "execution_time_seconds": round(self.get_execution_time(), 2),
            "peak_memory_mb": round(self.peak_memory, 2) if self.peak_memory else 0,
            "notes_processed": self.notes_processed,
            "ratings_processed": self.ratings_processed,
            "throughput_notes_per_second": round(self.get_throughput(), 2),
        }


class ScoreComparator:
    """Compare computed scores with original Community Notes scores."""

    def __init__(self, computed_scores: pd.DataFrame, original_scores: pd.DataFrame | None = None):
        self.computed_scores = computed_scores
        self.original_scores = original_scores
        self.comparison_results = {}

    def compare_scores(self):
        """Compare computed scores with original scores if available."""
        if self.original_scores is None or self.original_scores.empty:
            return {"comparison_available": False, "reason": "No original scores provided"}

        # Find common notes
        common_notes = set(self.computed_scores["noteId"]).intersection(
            set(self.original_scores["noteId"])
        )

        if not common_notes:
            return {"comparison_available": False, "reason": "No common notes found"}

        # Filter to common notes
        comp_df = self.computed_scores[self.computed_scores["noteId"].isin(common_notes)].set_index(
            "noteId"
        )
        orig_df = self.original_scores[self.original_scores["noteId"].isin(common_notes)].set_index(
            "noteId"
        )

        # Compare scores (assuming score columns exist)
        score_columns = ["coreNoteIntercept", "currentStatus", "finalRatingStatus"]
        comparison = {}

        for col in score_columns:
            if col in comp_df.columns and col in orig_df.columns:
                comp_values = comp_df[col].sort_index()
                orig_values = orig_df[col].sort_index()

                # Calculate metrics
                if pd.api.types.is_numeric_dtype(comp_values):
                    # For numeric scores
                    diff = comp_values - orig_values
                    comparison[col] = {
                        "mean_difference": float(diff.mean()) if not diff.isna().all() else None,
                        "std_difference": float(diff.std()) if not diff.isna().all() else None,
                        "correlation": float(comp_values.corr(orig_values))
                        if len(comp_values) > 1
                        else None,
                        "rmse": float(np.sqrt((diff**2).mean())) if not diff.isna().all() else None,
                    }
                else:
                    # For categorical scores
                    matches = (comp_values == orig_values).sum()
                    total = len(comp_values)
                    comparison[col] = {
                        "accuracy": matches / total if total > 0 else 0,
                        "matches": int(matches),
                        "total": int(total),
                    }

        return {
            "comparison_available": True,
            "common_notes_count": len(common_notes),
            "score_comparisons": comparison,
        }

    def find_discrepancies(self, threshold: float = 0.1):
        """Find notes with significant scoring discrepancies."""
        if self.original_scores is None or self.original_scores.empty:
            return []

        discrepancies = []

        # Find common notes with numeric scores
        common_notes = set(self.computed_scores["noteId"]).intersection(
            set(self.original_scores["noteId"])
        )

        if not common_notes:
            return discrepancies

        comp_df = self.computed_scores[self.computed_scores["noteId"].isin(common_notes)].set_index(
            "noteId"
        )
        orig_df = self.original_scores[self.original_scores["noteId"].isin(common_notes)].set_index(
            "noteId"
        )

        # Check for discrepancies in numeric scores
        if "coreNoteIntercept" in comp_df.columns and "coreNoteIntercept" in orig_df.columns:
            for note_id in common_notes:
                if note_id in comp_df.index and note_id in orig_df.index:
                    comp_score = comp_df.loc[note_id, "coreNoteIntercept"]
                    orig_score = orig_df.loc[note_id, "coreNoteIntercept"]

                    if pd.notna(comp_score) and pd.notna(orig_score):
                        diff = abs(comp_score - orig_score)
                        if diff > threshold:
                            discrepancies.append(
                                {
                                    "noteId": note_id,
                                    "computed_score": float(comp_score),
                                    "original_score": float(orig_score),
                                    "difference": float(diff),
                                }
                            )

        return sorted(discrepancies, key=lambda x: x["difference"], reverse=True)[
            :10
        ]  # Top 10 discrepancies


class CommunityNotesScoringRunner:
    """Main class to run Community Notes scoring on sampled data."""

    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_sample_data(self, sample_size: str) -> tuple[Path, dict[str, int]]:
        """Load sampled dataset files."""
        sample_dir = self.data_dir / f"sample_{sample_size}"

        if not sample_dir.exists():
            raise FileNotFoundError(f"Sample directory not found: {sample_dir}")

        # Check for required files
        required_files = {
            "notes": ["notes.tsv", "notes-00000.tsv"],
            "ratings": ["ratings.tsv"],
            "userEnrollment": ["userEnrollment.tsv", "userEnrollment-00000.tsv"],
            "noteStatusHistory": ["noteStatusHistory.tsv", "noteStatusHistory-00000.tsv"],
        }

        file_paths = {}
        file_counts = {}

        for file_type, possible_names in required_files.items():
            for name in possible_names:
                file_path = sample_dir / name
                if file_path.exists():
                    file_paths[file_type] = file_path
                    # Count rows (excluding header)
                    with file_path.open() as f:
                        file_counts[file_type] = sum(1 for _ in f) - 1
                    break
            else:
                print(f"Warning: {file_type} file not found in {sample_dir}")
                file_paths[file_type] = None
                file_counts[file_type] = 0

        return sample_dir, file_paths, file_counts

    def run_scoring(  # noqa: PLR0912
        self,
        sample_size: str,
        compare_original: bool = False,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Run scoring algorithm on a sample dataset.

        Orchestrates data loading, scoring execution, comparison, and statistics generation.
        """

        print(f"\n{'=' * 60}")
        print(f"Running scoring on {sample_size} sample dataset")
        print(f"{'=' * 60}")

        # Initialize metrics
        metrics = PerformanceMetrics()

        try:
            # Load sample data
            sample_dir, file_paths, file_counts = self.load_sample_data(sample_size)

            if not all(file_paths.values()):
                raise ValueError(f"Missing required files in {sample_dir}")

            print(f"Loaded sample data from: {sample_dir}")
            print(f"  Notes: {file_counts['notes']:,}")
            print(f"  Ratings: {file_counts['ratings']:,}")
            print(f"  User Enrollment: {file_counts['userEnrollment']:,}")
            print(f"  Note Status History: {file_counts['noteStatusHistory']:,}")

            # Prepare arguments for Community Notes scorer
            # For small samples, use simplified scoring to avoid clustering issues
            args = argparse.Namespace(
                notes=str(file_paths["notes"]),
                ratings=str(file_paths["ratings"]),
                enrollment=str(file_paths["userEnrollment"]),
                status=str(file_paths["noteStatusHistory"]),
                outdir=str(self.output_dir / f"scoring_{sample_size}"),
                headers=True,
                seed=42,
                pseudoraters=False,  # Disable for faster execution
                scorers="MFCoreScorer",  # Use simplified scorer for small samples
                strict_columns=False,  # Allow flexibility for sample data
                parallel=False,
                no_parquet=True,  # Only output TSV for simplicity
                check_flips=False,
                enforce_types=False,
                epoch_millis=None,
                cutoffTimestampMillis=None,
                excludeRatingsAfterANoteGotFirstStatusPlusNHours=None,
                daysInPastToApplyPostFirstStatusFiltering=14,
                prescoring_delay_hours=None,
                sample_ratings=0.0,
                previous_scored_notes=None,
                previous_aux_note_info=None,
                previous_rating_cutoff_millis=None,
            )

            # Create output directory for this run
            Path(args.outdir).mkdir(parents=True, exist_ok=True)

            # Start performance tracking
            metrics.start_tracking()
            metrics.notes_processed = file_counts["notes"]
            metrics.ratings_processed = file_counts["ratings"]

            print("\nRunning scoring algorithm...")

            # Run the scorer
            _run_scorer(args=args)

            # Stop performance tracking
            metrics.stop_tracking()

            print(f"✓ Scoring completed in {metrics.get_execution_time():.2f} seconds")
            print(f"  Throughput: {metrics.get_throughput():.2f} notes/second")
            print(f"  Peak memory: {metrics.peak_memory:.2f} MB")

            # Load the results
            scored_notes_path = Path(args.outdir) / "scored_notes.tsv"
            helpfulness_path = Path(args.outdir) / "helpfulness_scores.tsv"

            scored_notes = pd.read_csv(scored_notes_path, sep="\t")
            helpfulness_scores = pd.read_csv(helpfulness_path, sep="\t")

            print("\nResults generated:")
            print(f"  Scored notes: {len(scored_notes):,}")
            print(f"  Helpfulness scores: {len(helpfulness_scores):,}")

            # Compare with original scores if requested
            comparison_results = {}
            if compare_original:
                print("\nComparing with original scores...")

                # Try to load original scored notes from the sample
                original_status_path = file_paths.get("noteStatusHistory")
                if original_status_path and original_status_path.exists():
                    original_status = pd.read_csv(original_status_path, sep="\t")

                    comparator = ScoreComparator(scored_notes, original_status)
                    comparison_results = comparator.compare_scores()
                    discrepancies = comparator.find_discrepancies()

                    if comparison_results.get("comparison_available"):
                        print(
                            f"  Common notes compared: {comparison_results['common_notes_count']:,}"
                        )

                        # Print score comparisons
                        for score_type, metrics_dict in comparison_results.get(
                            "score_comparisons", {}
                        ).items():
                            print(f"  {score_type}:")
                            for metric_name, value in metrics_dict.items():
                                if value is not None:
                                    print(
                                        f"    {metric_name}: {value:.4f}"
                                        if isinstance(value, float)
                                        else f"    {metric_name}: {value}"
                                    )

                    if discrepancies:
                        comparison_results["top_discrepancies"] = discrepancies
                        print(f"\n  Top discrepancies found: {len(discrepancies)}")
                else:
                    print("  Original scores not available for comparison")

            # Prepare results
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            results = {
                "sample_size": sample_size,
                "timestamp": timestamp,
                "file_counts": file_counts,
                "performance_metrics": metrics.to_dict(),
                "scoring_results": {
                    "notes_scored": len(scored_notes),
                    "users_with_helpfulness": len(helpfulness_scores),
                    "unique_note_statuses": scored_notes["currentStatus"].value_counts().to_dict()
                    if "currentStatus" in scored_notes
                    else {},
                },
            }

            if comparison_results:
                results["comparison"] = comparison_results

            # Add summary statistics
            if "coreNoteIntercept" in scored_notes.columns:
                scores = scored_notes["coreNoteIntercept"].dropna()
                results["scoring_results"]["score_statistics"] = {
                    "mean": float(scores.mean()),
                    "std": float(scores.std()),
                    "min": float(scores.min()),
                    "max": float(scores.max()),
                    "median": float(scores.median()),
                }

            # Save results
            output_filename = f"scoring_results_{sample_size}_{timestamp}"

            if output_format == "json":
                output_path = self.output_dir / f"{output_filename}.json"
                with output_path.open("w") as f:
                    json.dump(results, f, indent=2, default=str)
                print(f"\n✓ Results saved to: {output_path}")

            elif output_format == "csv":
                # Save detailed results as CSV
                scored_notes_output = (
                    self.output_dir / f"scored_notes_{sample_size}_{timestamp}.csv"
                )
                helpfulness_output = self.output_dir / f"helpfulness_{sample_size}_{timestamp}.csv"

                scored_notes.to_csv(scored_notes_output, index=False)
                helpfulness_scores.to_csv(helpfulness_output, index=False)

                # Save metrics as JSON
                metrics_path = self.output_dir / f"metrics_{sample_size}_{timestamp}.json"
                with metrics_path.open("w") as f:
                    json.dump(results, f, indent=2, default=str)

                print("\n✓ Results saved to:")
                print(f"  {scored_notes_output}")
                print(f"  {helpfulness_output}")
                print(f"  {metrics_path}")

            return results

        except Exception as e:
            print(f"\n✗ Error running scoring on {sample_size}: {e}")
            import traceback

            traceback.print_exc()
            return {
                "sample_size": sample_size,
                "error": str(e),
                "performance_metrics": metrics.to_dict() if metrics else {},
            }


def main():
    """Main entry point for the scoring runner."""
    parser = argparse.ArgumentParser(
        description="Run Community Notes scoring algorithm on sampled datasets"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "communitynotes_data" / "samples",
        help="Path to directory containing sample datasets",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "scoring_results",
        help="Directory to save scoring results",
    )
    parser.add_argument(
        "--sample-size",
        choices=["1k", "10k", "100k"],
        help="Sample size to process (1k, 10k, or 100k)",
    )
    parser.add_argument(
        "--all-samples",
        action="store_true",
        help="Process all available sample sizes",
    )
    parser.add_argument(
        "--compare-original",
        action="store_true",
        help="Compare computed scores with original Community Notes scores",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "csv"],
        default="json",
        help="Output format for results (json or csv)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.sample_size and not args.all_samples:
        parser.error("Either --sample-size or --all-samples must be specified")

    if not args.data_dir.exists():
        parser.error(f"Data directory not found: {args.data_dir}")

    # Initialize runner
    runner = CommunityNotesScoringRunner(args.data_dir, args.output_dir)

    # Determine which samples to process
    if args.all_samples:
        # Find all available sample sizes
        sample_sizes = []
        for sample_dir in args.data_dir.glob("sample_*"):
            if sample_dir.is_dir():
                size = sample_dir.name.replace("sample_", "")
                if size in ["1k", "10k", "100k", "0k"]:  # Include 0k for tiny test samples
                    sample_sizes.append(size)
        sample_sizes.sort(key=lambda x: int(x.replace("k", "")) if x != "0k" else 0)
    else:
        sample_sizes = [args.sample_size]

    if not sample_sizes:
        print(f"No sample datasets found in {args.data_dir}")
        return 1

    print("Community Notes Scoring Runner")
    print(f"Data directory: {args.data_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Samples to process: {', '.join(sample_sizes)}")

    # Process each sample
    all_results = []
    for sample_size in sample_sizes:
        results = runner.run_scoring(
            sample_size,
            compare_original=args.compare_original,
            output_format=args.output_format,
        )
        all_results.append(results)

    # Save summary if processing multiple samples
    if len(all_results) > 1:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        summary_path = args.output_dir / f"scoring_summary_{timestamp}.json"

        summary = {
            "timestamp": timestamp,
            "samples_processed": len(all_results),
            "results": all_results,
        }

        with summary_path.open("w") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n{'=' * 60}")
        print(f"Summary saved to: {summary_path}")

        # Print performance comparison
        print("\nPerformance Summary:")
        for result in all_results:
            if "error" not in result:
                size = result["sample_size"]
                metrics = result["performance_metrics"]
                print(
                    f"  {size}: {metrics['execution_time_seconds']:.2f}s, "
                    f"{metrics['throughput_notes_per_second']:.2f} notes/sec, "
                    f"{metrics['peak_memory_mb']:.2f} MB"
                )

    print("\n✓ All scoring runs completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
