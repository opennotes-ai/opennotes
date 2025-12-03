#!/usr/bin/env python3
"""
Community Notes Data Processing Script

This script processes Community Notes data archives by:
1. Extracting ZIP archives
2. Merging multi-part ratings files
3. Anonymizing user identifiers
4. Creating sampled subsets with referential integrity
5. Validating data schemas
6. Compressing intermediate files with qsv snappy format

Usage:
    uv run python scripts/process_community_notes_data.py --help
    uv run python scripts/process_community_notes_data.py --extract --merge
    uv run python scripts/process_community_notes_data.py --anonymize --salt "your-salt-here"
    uv run python scripts/process_community_notes_data.py --sample 1000 10000 100000
    uv run python scripts/process_community_notes_data.py --compress-only
    uv run python scripts/process_community_notes_data.py --validate-only

Directory Structure Created:
    communitynotes_data/
    ├── archives/           # Original ZIP files
    ├── extracted/          # Extracted TSV files
    ├── merged/             # Combined datasets (ratings parts merged)
    ├── anonymized/         # Privacy-safe versions
    └── samples/            # Configurable subsets (sample_1k/, sample_10k/, etc.)
"""

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, ClassVar

import click
import polars as pl
from tqdm import tqdm


class CommunityNotesProcessor:
    """Process Community Notes data archives with extraction, merging, anonymization, and sampling."""

    EXPECTED_SCHEMAS: ClassVar[dict[str, list[str]]] = {
        "notes": [
            "noteId",
            "noteAuthorParticipantId",
            "createdAtMillis",
            "tweetId",
            "classification",
            "believable",
            "harmful",
            "validationDifficulty",
            "misleadingOther",
            "misleadingFactualError",
            "misleadingManipulatedMedia",
            "misleadingOutdatedInformation",
            "misleadingMissingImportantContext",
            "misleadingUnverifiedClaimAsFact",
            "misleadingSatire",
            "notMisleadingOther",
            "notMisleadingFactuallyCorrect",
            "notMisleadingOutdatedButNotWhenWritten",
            "notMisleadingClearlySatire",
            "notMisleadingPersonalOpinion",
            "trustworthySources",
            "summary",
            "isMediaNote",
        ],
        "ratings": [
            "noteId",
            "raterParticipantId",
            "createdAtMillis",
            "version",
            "agree",
            "disagree",
            "helpful",
            "notHelpful",
            "helpfulnessLevel",
            "helpfulOther",
            "helpfulInformative",
            "helpfulClear",
            "helpfulEmpathetic",
            "helpfulGoodSources",
            "helpfulUniqueContext",
            "helpfulAddressesClaim",
            "helpfulImportantContext",
            "helpfulUnbiasedLanguage",
            "notHelpfulOther",
            "notHelpfulIncorrect",
            "notHelpfulSourcesMissingOrUnreliable",
            "notHelpfulOpinionSpeculationOrBias",
            "notHelpfulMissingKeyPoints",
            "notHelpfulOutdated",
            "notHelpfulHardToUnderstand",
            "notHelpfulArgumentativeOrBiased",
            "notHelpfulOffTopic",
            "notHelpfulSpamHarassmentOrAbuse",
            "notHelpfulIrrelevantSources",
            "notHelpfulOpinionSpeculation",
            "notHelpfulNoteNotNeeded",
            "ratedOnTweetId",
            "ratingSourceBucketed",
        ],
        "userEnrollment": [
            "participantId",
            "enrollmentState",
            "successfulRatingNeededToEarnIn",
            "timestampOfLastStateChange",
            "timestampOfLastEarnOut",
            "modelingPopulation",
            "modelingGroup",
            "numberOfTimesEarnedOut",
        ],
        "noteStatusHistory": [
            "noteId",
            "noteAuthorParticipantId",
            "createdAtMillis",
            "timestampMillisOfFirstNonNMRStatus",
            "firstNonNMRStatus",
            "currentStatus",
            "currentCoreStatus",
            "currentExpansionStatus",
            "currentMultiGroupStatus",
            "currentDecidedBy",
            "currentModelingGroup",
            "currentModelingMultiGroup",
            "timestampMillisOfCurrentStatus",
            "timestampMillisOfLatestNonNMRStatus",
            "timestampMillisOfRetroLock",
            "mostRecentNonNMRStatus",
            "timestampMillisOfStatusLock",
            "timestampMillisOfMostRecentStatusChange",
            "lockedStatus",
            "timestampMillisOfNmrDueToMinStableCrhTime",
            "timestampMinuteOfFinalScoringOutput",
        ],
        "noteRequests": [
            "userId",
            "tweetId",
            "createdAtMillis",
            "sourceLink",
        ],
    }

    def __init__(self, data_dir: Path, verbose: bool = True) -> None:
        """Initialize processor with data directory.

        Args:
            data_dir: Path to communitynotes_data directory
            verbose: Enable verbose output
        """
        self.data_dir = data_dir
        self.verbose = verbose
        self.user_mapping: dict[str, str] = {}

        self.archives_dir = data_dir / "archives"
        self.extracted_dir = data_dir / "extracted"
        self.merged_dir = data_dir / "merged"
        self.anonymized_dir = data_dir / "anonymized"
        self.samples_dir = data_dir / "samples"

    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            click.echo(message)

    def find_data_file(self, directory: Path, filename: str) -> Path:
        """Find data file, preferring compressed .sz version if available.

        Args:
            directory: Directory to search in
            filename: Base filename (without .sz extension)

        Returns:
            Path to the file (compressed or uncompressed)

        Raises:
            FileNotFoundError: If neither compressed nor uncompressed version exists
        """
        # Check if filename already has .sz extension
        if filename.endswith(".sz"):
            compressed = directory / filename
            uncompressed = directory / filename[:-3]  # Remove .sz
        else:
            compressed = directory / f"{filename}.sz"
            uncompressed = directory / filename

        # Prefer compressed version if both exist
        if compressed.exists():
            return compressed
        if uncompressed.exists():
            return uncompressed
        raise FileNotFoundError(f"Neither {filename} nor {filename}.sz found in {directory}")

    def _ensure_directories(self) -> None:
        """Create directory structure if it doesn't exist."""
        for directory in [
            self.archives_dir,
            self.extracted_dir,
            self.merged_dir,
            self.anonymized_dir,
            self.samples_dir,
        ]:
            directory.mkdir(exist_ok=True)

    def _move_archives(self) -> None:
        """Move ZIP files to archives directory."""
        zip_files = list(self.data_dir.glob("*.zip"))
        if not zip_files:
            self._log("No ZIP files to move")
            return

        self._log(f"Moving {len(zip_files)} ZIP files to archives/")
        for zip_file in zip_files:
            dest = self.archives_dir / zip_file.name
            if not dest.exists():
                shutil.move(str(zip_file), str(dest))

    def extract_archives(self) -> None:
        """Extract ZIP archives to extracted/ directory."""
        self._ensure_directories()
        self._move_archives()

        zip_files = sorted(self.archives_dir.glob("*.zip"))
        if not zip_files:
            raise click.ClickException("No ZIP files found in archives/")

        self._log(f"\nExtracting {len(zip_files)} ZIP archives...")

        with tqdm(zip_files, desc="Extracting", disable=not self.verbose) as pbar:
            for zip_path in pbar:
                pbar.set_description(f"Extracting {zip_path.name}")

                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    for member in zip_ref.namelist():
                        if member.endswith(".tsv"):
                            extract_path = self.extracted_dir / member
                            if not extract_path.exists():
                                zip_ref.extract(member, self.extracted_dir)

        self._log(f"✓ Extracted to {self.extracted_dir}")

    def merge_ratings(self, compress_output: bool = False) -> None:
        """Merge multi-part ratings files using streaming to avoid memory issues.

        Args:
            compress_output: If True, compress the output file after merging
        """
        ratings_files = sorted(self.extracted_dir.glob("ratings-*.tsv"))
        if not ratings_files:
            raise click.ClickException("No ratings files found in extracted/")

        merged_path = self.merged_dir / "ratings.tsv"

        self._log(f"\nMerging {len(ratings_files)} ratings files...")
        self._log(f"Output: {merged_path}")

        first_file = True
        with (
            merged_path.open("w") as outfile,
            tqdm(ratings_files, desc="Merging", disable=not self.verbose) as pbar,
        ):
            for ratings_file in pbar:
                pbar.set_description(f"Processing {ratings_file.name}")

                with ratings_file.open() as infile:
                    header = infile.readline()

                    if first_file:
                        outfile.write(header)
                        first_file = False

                    for line in infile:
                        outfile.write(line)

        file_size = merged_path.stat().st_size / (1024**3)
        self._log(f"✓ Merged ratings file: {file_size:.2f} GB")

        # Optionally compress the merged ratings file
        if compress_output:
            self._log("  → Compressing merged ratings file...")
            compressed_path = merged_path.with_suffix(".tsv.sz")
            cpu_cores = max(1, os.cpu_count() - 1) if os.cpu_count() else 4
            result = subprocess.run(
                [
                    "qsv",
                    "snappy",
                    "compress",
                    str(merged_path),
                    "-o",
                    str(compressed_path),
                    "--jobs",
                    str(cpu_cores),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                compressed_size = compressed_path.stat().st_size / (1024**3)
                saved = file_size - compressed_size
                self._log(f"  ✓ Compressed to {compressed_size:.2f} GB (saved {saved:.2f} GB)")
                merged_path.unlink()  # Remove uncompressed version
            else:
                self._log(f"  ✗ Compression failed: {result.stderr}")

        self._log("\nCopying non-ratings files to merged/")
        for other_file in self.extracted_dir.glob("*.tsv"):
            if not other_file.name.startswith("ratings-"):
                dest = self.merged_dir / other_file.name
                if not dest.exists():
                    shutil.copy(other_file, dest)
                    self._log(f"  ✓ Copied {other_file.name}")

        bat_signals = self.merged_dir / "batSignals-00000.tsv"
        if bat_signals.exists():
            note_requests = self.merged_dir / "noteRequests.tsv"
            bat_signals.rename(note_requests)
            self._log("✓ Renamed batSignals to noteRequests")

    def _anonymize_id(self, user_id: str, salt: str) -> str:
        """Anonymize a user ID with consistent mapping.

        Args:
            user_id: Original participant ID (already hashed)
            salt: Salt for additional hashing layer

        Returns:
            Anonymized ID (64-char hex string)
        """
        if user_id in self.user_mapping:
            return self.user_mapping[user_id]

        anonymized = hashlib.sha256(f"{user_id}{salt}".encode()).hexdigest()
        self.user_mapping[user_id] = anonymized
        return anonymized

    def anonymize_data(self, salt: str) -> None:
        """Apply additional anonymization layer to all datasets.

        Args:
            salt: Salt for hashing user identifiers
        """
        if not salt:
            raise click.ClickException("Salt must be provided for anonymization")

        merged_files = list(self.merged_dir.glob("*.tsv"))
        if not merged_files:
            raise click.ClickException("No merged files found. Run --merge first.")

        self._log(f"\nAnonymizing {len(merged_files)} datasets...")

        user_id_columns = {
            "notes-00000.tsv": ["noteAuthorParticipantId"],
            "ratings.tsv": ["raterParticipantId"],
            "userEnrollment-00000.tsv": ["participantId"],
            "noteStatusHistory-00000.tsv": ["noteAuthorParticipantId"],
            "noteRequests.tsv": ["userId"],
        }

        with tqdm(merged_files, desc="Anonymizing", disable=not self.verbose) as pbar:
            for file_path in pbar:
                pbar.set_description(f"Anonymizing {file_path.name}")

                columns_to_anonymize = user_id_columns.get(file_path.name, [])
                if not columns_to_anonymize:
                    dest = self.anonymized_dir / file_path.name
                    shutil.copy(file_path, dest)
                    continue

                df = pl.read_csv(file_path, separator="\t", infer_schema_length=10000)

                for col in columns_to_anonymize:
                    if col in df.columns:
                        df = df.with_columns(
                            pl.col(col)
                            .map_elements(
                                lambda x: self._anonymize_id(x, salt), return_dtype=pl.Utf8
                            )
                            .alias(col)
                        )

                output_path = self.anonymized_dir / file_path.name
                df.write_csv(output_path, separator="\t")

        mapping_path = self.anonymized_dir / "user_mapping.json"
        with mapping_path.open("w") as f:
            json.dump(self.user_mapping, f, indent=2)

        self._log(f"✓ Anonymized {len(merged_files)} files")
        self._log(f"✓ User mapping saved to {mapping_path}")

    def create_samples(self, sizes: list[int]) -> None:  # noqa: PLR0912
        """Create sampled subsets with referential integrity.

        Handles multiple file types, compression formats, and referential integrity.

        Args:
            sizes: List of sample sizes (e.g., [1000, 10000, 100000])
        """
        has_anonymized = self.anonymized_dir.exists() and (
            len(list(self.anonymized_dir.glob("*.tsv"))) > 0
            or len(list(self.anonymized_dir.glob("*.tsv.sz"))) > 0
        )
        source_dir = self.anonymized_dir if has_anonymized else self.merged_dir

        # Try to find notes file - check both names and compressed versions
        try:
            notes_file = self.find_data_file(source_dir, "notes-00000.tsv")
        except FileNotFoundError:
            try:
                notes_file = self.find_data_file(source_dir, "notes.tsv")
            except FileNotFoundError:
                raise click.ClickException(f"Notes file not found in {source_dir}")

        self._log(f"\nCreating {len(sizes)} sample sets from {source_dir.name}/")

        for size in sizes:
            sample_dir = self.samples_dir / f"sample_{size // 1000}k"
            sample_dir.mkdir(exist_ok=True)

            self._log(f"\n→ Creating sample of {size:,} notes in {sample_dir.name}/")

            # Handle compressed files using qsv
            if notes_file.suffix == ".sz":
                # First get the total count
                count_result = subprocess.run(
                    ["qsv", "count", str(notes_file)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                total_count = (
                    int(count_result.stdout.strip()) if count_result.returncode == 0 else 0
                )

                if total_count < size:
                    self._log(f"Warning: Requested {size} notes but only {total_count} available")
                    # Use qsv to decompress and read all data
                    sample_result = subprocess.run(
                        ["qsv", "cat", "rows", str(notes_file)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if sample_result.returncode == 0:
                        # Save the output to a temporary file and read with polars
                        temp_file = sample_dir / "temp_notes.tsv"
                        temp_file.write_text(sample_result.stdout)
                        sample_notes = pl.read_csv(
                            temp_file, separator="\t", infer_schema_length=10000
                        )
                        temp_file.unlink()
                    else:
                        raise click.ClickException(
                            f"Failed to read compressed notes file: {sample_result.stderr}"
                        )
                else:
                    # Use qsv sample command for compressed files
                    sample_result = subprocess.run(
                        ["qsv", "sample", str(size), str(notes_file), "--seed", "42"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if sample_result.returncode == 0:
                        # Save the output to a temporary file and read with polars
                        temp_file = sample_dir / "temp_notes.tsv"
                        temp_file.write_text(sample_result.stdout)
                        sample_notes = pl.read_csv(
                            temp_file, separator="\t", infer_schema_length=10000
                        )
                        temp_file.unlink()
                    else:
                        raise click.ClickException(
                            f"Failed to sample from compressed notes file: {sample_result.stderr}"
                        )
            else:
                # For uncompressed files, use polars as before
                notes_df = pl.read_csv(notes_file, separator="\t", infer_schema_length=10000)

                if len(notes_df) < size:
                    self._log(f"Warning: Requested {size} notes but only {len(notes_df)} available")
                    sample_notes = notes_df
                else:
                    sample_notes = notes_df.sample(n=size, seed=42)

            sampled_note_ids = set(sample_notes["noteId"].to_list())
            sampled_user_ids = set(sample_notes["noteAuthorParticipantId"].to_list())

            sample_notes.write_csv(sample_dir / "notes.tsv", separator="\t")
            self._log(f"  ✓ notes.tsv: {len(sample_notes):,} rows")

            # Try to find ratings file
            try:
                ratings_file = self.find_data_file(source_dir, "ratings.tsv")
            except FileNotFoundError:
                ratings_file = None

            if ratings_file:
                self._log("  → Filtering ratings (scanning large file)...")

                note_ids_str = "|".join(str(nid) for nid in sampled_note_ids)
                result = subprocess.run(
                    ["qsv", "search", "-s", "noteId", note_ids_str, str(ratings_file)],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode == 0 and result.stdout.strip():
                    output_path = sample_dir / "ratings.tsv"
                    with output_path.open("w") as f:
                        f.write(result.stdout)

                    try:
                        rating_df = pl.read_csv(
                            output_path, separator="\t", infer_schema_length=10000
                        )
                        if len(rating_df) > 0:
                            rater_ids = set(rating_df["raterParticipantId"].to_list())
                            sampled_user_ids.update(rater_ids)
                            self._log(f"  ✓ ratings.tsv: {len(rating_df):,} rows")
                        else:
                            self._log("  ✓ ratings.tsv: 0 rows (no ratings for sampled notes)")
                    except Exception:
                        self._log("  Warning: Could not parse qsv output, using polars fallback")
                        ratings_df = pl.read_csv(
                            ratings_file, separator="\t", infer_schema_length=10000
                        )
                        sample_ratings = ratings_df.filter(pl.col("noteId").is_in(sampled_note_ids))
                        sample_ratings.write_csv(sample_dir / "ratings.tsv", separator="\t")
                        if len(sample_ratings) > 0:
                            rater_ids = set(sample_ratings["raterParticipantId"].to_list())
                            sampled_user_ids.update(rater_ids)
                        self._log(f"  ✓ ratings.tsv: {len(sample_ratings):,} rows")
                else:
                    self._log("  Warning: qsv search failed, using polars fallback")
                    ratings_df = pl.read_csv(
                        ratings_file, separator="\t", infer_schema_length=10000
                    )
                    sample_ratings = ratings_df.filter(pl.col("noteId").is_in(sampled_note_ids))
                    sample_ratings.write_csv(sample_dir / "ratings.tsv", separator="\t")
                    rater_ids = set(sample_ratings["raterParticipantId"].to_list())
                    sampled_user_ids.update(rater_ids)
                    self._log(f"  ✓ ratings.tsv: {len(sample_ratings):,} rows")

            # Try to find user enrollment file
            try:
                enrollment_file = self.find_data_file(source_dir, "userEnrollment-00000.tsv")
            except FileNotFoundError:
                try:
                    enrollment_file = self.find_data_file(source_dir, "userEnrollment.tsv")
                except FileNotFoundError:
                    enrollment_file = None

            if enrollment_file:
                enrollment_df = pl.read_csv(
                    enrollment_file, separator="\t", infer_schema_length=10000
                )
                sample_enrollment = enrollment_df.filter(
                    pl.col("participantId").is_in(sampled_user_ids)
                )
                sample_enrollment.write_csv(sample_dir / "userEnrollment.tsv", separator="\t")
                self._log(f"  ✓ userEnrollment.tsv: {len(sample_enrollment):,} rows")

            # Try to find note status history file
            try:
                status_file = self.find_data_file(source_dir, "noteStatusHistory-00000.tsv")
            except FileNotFoundError:
                try:
                    status_file = self.find_data_file(source_dir, "noteStatusHistory.tsv")
                except FileNotFoundError:
                    status_file = None

            if status_file:
                status_df = pl.read_csv(status_file, separator="\t", infer_schema_length=10000)
                sample_status = status_df.filter(pl.col("noteId").is_in(sampled_note_ids))
                sample_status.write_csv(sample_dir / "noteStatusHistory.tsv", separator="\t")
                self._log(f"  ✓ noteStatusHistory.tsv: {len(sample_status):,} rows")

            # Try to find note requests file
            try:
                requests_file = self.find_data_file(source_dir, "noteRequests.tsv")
            except FileNotFoundError:
                requests_file = None

            if requests_file:
                requests_df = pl.read_csv(requests_file, separator="\t", infer_schema_length=10000)

                if "tweetId" in sample_notes.columns:
                    tweet_ids = set(sample_notes["tweetId"].to_list())
                    sample_requests = requests_df.filter(pl.col("tweetId").is_in(tweet_ids))
                    sample_requests.write_csv(sample_dir / "noteRequests.tsv", separator="\t")
                    self._log(f"  ✓ noteRequests.tsv: {len(sample_requests):,} rows")

        self._log(f"\n✓ Created {len(sizes)} sample sets in {self.samples_dir}")

    def validate_schema(self) -> bool:  # noqa: PLR0912
        """Validate TSV files have expected columns and basic data integrity.

        Validates compressed files, polars operations, and qsv with fallbacks.

        Returns:
            True if validation passes, False otherwise
        """
        source_dir = self.merged_dir if self.merged_dir.exists() else self.extracted_dir

        tsv_files = {
            "notes-00000.tsv": "notes",
            "ratings.tsv": "ratings",
            "userEnrollment-00000.tsv": "userEnrollment",
            "noteStatusHistory-00000.tsv": "noteStatusHistory",
            "noteRequests.tsv": "noteRequests",
        }

        self._log(f"\nValidating schema for {len(tsv_files)} datasets...")

        all_valid = True
        validation_results: dict[str, dict[str, Any]] = {}

        for filename, schema_key in tsv_files.items():
            try:
                file_path = self.find_data_file(source_dir, filename)
            except FileNotFoundError:
                self._log(f"⚠ Skipping {filename} (not found)")
                continue

            self._log(f"\n→ Validating {file_path.name}")

            try:
                # For compressed files, use qsv to get headers
                if file_path.suffix == ".sz":
                    # Use qsv headers command which works with .sz files
                    headers_result = subprocess.run(
                        ["qsv", "headers", str(file_path)],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    # Parse the headers output (format: "1   column_name")
                    actual_columns = set()
                    for line in headers_result.stdout.strip().split("\n"):
                        # Split by spaces and take everything after the first element
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            actual_columns.add(parts[1])
                else:
                    # For uncompressed files, use polars
                    df = pl.read_csv(file_path, separator="\t", n_rows=1, infer_schema_length=1)
                    actual_columns = set(df.columns)

                expected_columns = set(self.EXPECTED_SCHEMAS[schema_key])

                missing_cols = expected_columns - actual_columns
                extra_cols = actual_columns - expected_columns

                is_valid = len(missing_cols) == 0

                if is_valid:
                    self._log(f"  ✓ Schema valid ({len(actual_columns)} columns)")
                else:
                    self._log("  ✗ Schema invalid")
                    all_valid = False

                if missing_cols:
                    self._log(f"  Missing columns: {sorted(missing_cols)}")

                if extra_cols:
                    self._log(f"  Extra columns: {sorted(extra_cols)}")

                try:
                    row_count_result = subprocess.run(
                        ["qsv", "count", str(file_path)], capture_output=True, text=True, check=True
                    )
                    row_count = int(row_count_result.stdout.strip())
                    self._log(f"  Rows: {row_count:,}")
                except (subprocess.CalledProcessError, ValueError):
                    self._log("  Rows: (unable to count - using wc fallback)")
                    wc_result = subprocess.run(
                        ["wc", "-l", str(file_path)], capture_output=True, text=True, check=True
                    )
                    row_count = int(wc_result.stdout.strip().split()[0]) - 1
                    self._log(f"  Rows: ~{row_count:,} (approximate)")

                validation_results[filename] = {
                    "valid": is_valid,
                    "columns": len(actual_columns),
                    "rows": row_count,
                    "missing_columns": sorted(missing_cols),
                    "extra_columns": sorted(extra_cols),
                }

            except Exception as e:
                self._log(f"  ✗ Validation error: {e}")
                all_valid = False
                validation_results[filename] = {"valid": False, "error": str(e)}

        self._log("\n" + "=" * 60)
        if all_valid:
            self._log("✓ All validations passed")
        else:
            self._log("✗ Some validations failed")
        self._log("=" * 60)

        return all_valid

    def compress_directories(  # noqa: PLR0912
        self, dirs: list[Path] | None = None, keep_originals: bool = False
    ) -> tuple[float, float]:
        """Compress TSV files using qsv snappy multithreaded compression.

        Manages multiple TSV files with progress tracking and calculations.

        Args:
            dirs: List of directories to compress. If None, compresses extracted/, merged/, and anonymized/
            keep_originals: If True, keep original files after compression

        Returns:
            Tuple of (original_size_gb, compressed_size_gb)
        """
        if dirs is None:
            # Default directories to compress
            dirs = []
            for dir_path in [self.extracted_dir, self.merged_dir, self.anonymized_dir]:
                if dir_path.exists() and any(dir_path.glob("*.tsv")):
                    dirs.append(dir_path)

        if not dirs:
            self._log("No directories with TSV files to compress")
            return (0.0, 0.0)

        self._log(f"\nCompressing TSV files in {len(dirs)} directories...")
        if keep_originals:
            self._log("  (keeping original files)")

        total_original_size = 0
        total_compressed_size = 0
        files_compressed = 0

        # Get available CPU cores (leave one free for system)
        cpu_cores = max(1, os.cpu_count() - 1) if os.cpu_count() else 4

        for dir_path in dirs:
            self._log(f"\n→ Compressing files in {dir_path.name}/")
            tsv_files = sorted(dir_path.glob("*.tsv"))

            if not tsv_files:
                self._log(f"  No TSV files found in {dir_path.name}")
                continue

            with tqdm(
                tsv_files, desc=f"Compressing {dir_path.name}", disable=not self.verbose
            ) as pbar:
                for tsv_file in pbar:
                    # Skip if compressed version already exists
                    compressed_file = tsv_file.with_suffix(".tsv.sz")
                    if compressed_file.exists():
                        pbar.set_description(f"Skipping {tsv_file.name} (already compressed)")
                        continue

                    pbar.set_description(f"Compressing {tsv_file.name}")
                    original_size = tsv_file.stat().st_size

                    # Use qsv snappy compress with multithreading
                    result = subprocess.run(
                        [
                            "qsv",
                            "snappy",
                            "compress",
                            str(tsv_file),
                            "-o",
                            str(compressed_file),
                            "--jobs",
                            str(cpu_cores),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    if result.returncode != 0:
                        self._log(f"  ✗ Failed to compress {tsv_file.name}: {result.stderr}")
                        continue

                    # Verify compressed file exists and is valid
                    if not compressed_file.exists():
                        self._log(f"  ✗ Compressed file not created for {tsv_file.name}")
                        continue

                    # Quick validation with qsv snappy check
                    check_result = subprocess.run(
                        ["qsv", "snappy", "check", str(compressed_file)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    if check_result.returncode != 0:
                        self._log(f"  ✗ Compressed file validation failed for {tsv_file.name}")
                        compressed_file.unlink()  # Remove invalid compressed file
                        continue

                    compressed_size = compressed_file.stat().st_size
                    total_original_size += original_size
                    total_compressed_size += compressed_size
                    files_compressed += 1

                    # Remove original if requested
                    if not keep_originals:
                        tsv_file.unlink()
                        pbar.set_description(f"Compressed {tsv_file.name} (removed original)")
                    else:
                        pbar.set_description(f"Compressed {tsv_file.name} (kept original)")

        # Convert to GB
        original_gb = total_original_size / (1024**3)
        compressed_gb = total_compressed_size / (1024**3)

        if files_compressed > 0:
            compression_ratio = total_original_size / total_compressed_size
            space_saved_gb = original_gb - compressed_gb
            space_saved_pct = (1 - (total_compressed_size / total_original_size)) * 100

            self._log(f"\n{'=' * 60}")
            self._log("Compression Summary:")
            self._log(f"  Files compressed: {files_compressed}")
            self._log(f"  Original size: {original_gb:.2f} GB")
            self._log(f"  Compressed size: {compressed_gb:.2f} GB")
            self._log(f"  Space saved: {space_saved_gb:.2f} GB ({space_saved_pct:.1f}%)")
            self._log(f"  Compression ratio: {compression_ratio:.2f}:1")
            self._log("=" * 60)
        else:
            self._log(
                "\n✓ No files needed compression (all already compressed or no TSV files found)"
            )

        return (original_gb, compressed_gb)


@click.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(__file__).parent.parent / "communitynotes_data",
    help="Path to communitynotes_data directory",
)
@click.option("--extract", is_flag=True, help="Extract ZIP archives")
@click.option("--merge", is_flag=True, help="Merge multi-part ratings files")
@click.option("--anonymize", is_flag=True, help="Anonymize user identifiers")
@click.option("--salt", type=str, help="Salt for anonymization (required with --anonymize)")
@click.option(
    "--sample",
    "sample_sizes",
    type=int,
    multiple=True,
    help="Create samples of specified sizes (can be used multiple times)",
)
@click.option("--compress", is_flag=True, help="Compress intermediate data files after processing")
@click.option("--compress-only", is_flag=True, help="Only compress existing data files")
@click.option("--keep-originals", is_flag=True, help="Keep original files after compression")
@click.option("--validate-only", is_flag=True, help="Only validate data schemas")
@click.option("--quiet", is_flag=True, help="Suppress verbose output")
def main(
    data_dir: Path,
    extract: bool,
    merge: bool,
    anonymize: bool,
    salt: str | None,
    sample_sizes: tuple[int, ...],
    compress: bool,
    compress_only: bool,
    keep_originals: bool,
    validate_only: bool,
    quiet: bool,
) -> None:
    """Process Community Notes data archives.

    This script handles extraction, merging, anonymization, sampling, validation,
    and compression of Community Notes datasets downloaded from Twitter/X.

    Examples:

        \b
        # Extract and merge data
        uv run python scripts/process_community_notes_data.py --extract --merge

        \b
        # Anonymize merged data
        uv run python scripts/process_community_notes_data.py --anonymize --salt "dev-2024"

        \b
        # Create multiple sample sizes
        uv run python scripts/process_community_notes_data.py --sample 1000 --sample 10000 --sample 100000

        \b
        # Full pipeline with compression
        uv run python scripts/process_community_notes_data.py --extract --merge --anonymize --salt "dev-2024" --sample 1000 --compress

        \b
        # Compress existing data only
        uv run python scripts/process_community_notes_data.py --compress-only

        \b
        # Compress keeping originals
        uv run python scripts/process_community_notes_data.py --compress-only --keep-originals

        \b
        # Validate data only
        uv run python scripts/process_community_notes_data.py --validate-only
    """
    processor = CommunityNotesProcessor(data_dir, verbose=not quiet)

    try:
        if validate_only:
            is_valid = processor.validate_schema()
            raise SystemExit(0 if is_valid else 1)

        if compress_only:
            # Only compress existing files
            processor.compress_directories(keep_originals=keep_originals)
            raise SystemExit(0)

        if not any([extract, merge, anonymize, sample_sizes, compress]):
            click.echo("No operations specified. Use --help for usage information.")
            raise SystemExit(1)

        if extract:
            processor.extract_archives()

        if merge:
            processor.merge_ratings()

        if anonymize:
            if not salt:
                raise click.ClickException("--salt is required when using --anonymize")
            processor.anonymize_data(salt)

        if sample_sizes:
            processor.create_samples(list(sample_sizes))

        if compress:
            # Compress after all other operations
            processor.compress_directories(keep_originals=keep_originals)

        click.echo("\n✓ All operations completed successfully")

    except click.ClickException:
        raise
    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
