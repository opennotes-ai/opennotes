#!/usr/bin/env python3

import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.notes import loaders as note_loaders
from src.notes.models import Note, Rating
from src.scoring_adapter import ScoringAdapter

scoring_constants_path = Path(__file__).parent.parent.parent / "communitynotes" / "scoring" / "src"
sys.path.insert(0, str(scoring_constants_path))

from scoring.constants import (  # noqa: E402 - sys.path manipulation required before import
    core,
    createdAtMillisKey,
    currentCoreStatusKey,
    currentDecidedByKey,
    currentExpansionStatusKey,
    currentGroupStatusKey,
    currentLabelKey,
    currentModelingGroupKey,
    currentModelingMultiGroupKey,
    currentMultiGroupStatusKey,
    earnedIn,
    enrollmentState,
    firstNonNMRLabelKey,
    lockedStatusKey,
    modelingGroupKey,
    modelingPopulationKey,
    mostRecentNonNMRLabelKey,
    noteAuthorParticipantIdKey,
    noteIdKey,
    numberOfTimesEarnedOutKey,
    participantIdKey,
    successfulRatingNeededToEarnIn,
    timestampMillisOfFirstNmrDueToMinStableCrhTimeKey,
    timestampMillisOfMostRecentStatusChangeKey,
    timestampMillisOfNmrDueToMinStableCrhTimeKey,
    timestampMillisOfNoteCurrentLabelKey,
    timestampMillisOfNoteFirstNonNMRLabelKey,
    timestampMillisOfNoteMostRecentNonNMRLabelKey,
    timestampMillisOfRetroLockKey,
    timestampMillisOfStatusLockKey,
    timestampMinuteOfFinalScoringOutput,
    timestampOfLastEarnOut,
    timestampOfLastStateChange,
)


class ScoringValidator:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.scoring_adapter = ScoringAdapter()
        self.validation_results = {
            "timestamp": datetime.now(UTC).isoformat(),
            "notes_processed": 0,
            "notes_scored": 0,
            "errors": [],
            "score_distribution": {},
            "status_transitions": {},
            "edge_cases": [],
            "recommendations": [],
        }

    async def fetch_notes_and_ratings(self) -> tuple[list[Note], list[Rating]]:
        print("Fetching notes and ratings from database...")

        result = await self.session.execute(select(Note).options(*note_loaders.full()))
        notes = result.scalars().all()

        result = await self.session.execute(select(Rating))
        ratings = result.scalars().all()

        print(f"Found {len(notes)} notes with {len(ratings)} ratings")
        self.validation_results["notes_processed"] = len(notes)

        return notes, ratings

    def prepare_scoring_data(
        self, notes: list[Note], ratings: list[Rating]
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        import math

        print("\nPreparing data for scoring algorithm...")

        notes_data = []
        ratings_data = []
        status_data = []
        participant_ids = set()

        for note in notes:
            created_at_millis = int(note.created_at.timestamp() * 1000)

            # Get platform_message_id from message archive via request relationship
            platform_message_id = None
            if note.request and note.request.message_archive:
                platform_message_id = note.request.message_archive.platform_message_id

            notes_data.append(
                {
                    "noteId": note.note_id,
                    "noteAuthorParticipantId": note.author_participant_id,
                    "createdAtMillis": created_at_millis,
                    "tweetId": platform_message_id or "0",
                    "summary": note.summary,
                    "classification": note.classification,
                }
            )

            status_data.append(
                {
                    noteIdKey: note.note_id,
                    noteAuthorParticipantIdKey: note.author_participant_id,
                    createdAtMillisKey: created_at_millis,
                    timestampMillisOfNoteFirstNonNMRLabelKey: math.nan,
                    firstNonNMRLabelKey: None,
                    timestampMillisOfNoteCurrentLabelKey: math.nan,
                    currentLabelKey: "NEEDS_MORE_RATINGS",
                    timestampMillisOfNoteMostRecentNonNMRLabelKey: math.nan,
                    mostRecentNonNMRLabelKey: None,
                    timestampMillisOfStatusLockKey: math.nan,
                    lockedStatusKey: None,
                    timestampMillisOfRetroLockKey: math.nan,
                    currentCoreStatusKey: "NEEDS_MORE_RATINGS",
                    currentExpansionStatusKey: None,
                    currentGroupStatusKey: None,
                    currentDecidedByKey: None,
                    currentModelingGroupKey: math.nan,
                    timestampMillisOfMostRecentStatusChangeKey: float(created_at_millis),
                    timestampMillisOfNmrDueToMinStableCrhTimeKey: math.nan,
                    currentMultiGroupStatusKey: None,
                    currentModelingMultiGroupKey: math.nan,
                    timestampMinuteOfFinalScoringOutput: math.nan,
                    timestampMillisOfFirstNmrDueToMinStableCrhTimeKey: math.nan,
                    "classification": note.classification,
                }
            )

            participant_ids.add(note.author_participant_id)

        helpful_tags = [
            "helpfulOther",
            "helpfulInformative",
            "helpfulClear",
            "helpfulEmpathetic",
            "helpfulGoodSources",
            "helpfulUniqueContext",
            "helpfulAddressesClaim",
            "helpfulImportantContext",
            "helpfulUnbiasedLanguage",
        ]

        not_helpful_tags = [
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
        ]

        for rating in ratings:
            helpfulness_level = rating.helpfulness_level
            helpful_num = {"HELPFUL": 1.0, "SOMEWHAT_HELPFUL": 0.5, "NOT_HELPFUL": 0.0}.get(
                helpfulness_level, 0.0
            )

            rating_data = {
                "raterParticipantId": rating.rater_participant_id,
                "noteId": rating.note_id,
                "createdAtMillis": int(rating.created_at.timestamp() * 1000),
                "helpfulnessLevel": helpfulness_level,
                "helpfulNum": helpful_num,
                "highVolumeRater": False,
                "correlatedRater": False,
                "ratingSourceBucketed": "DEFAULT",
            }

            for tag in helpful_tags:
                rating_data[tag] = 0

            for tag in not_helpful_tags:
                rating_data[tag] = 0

            ratings_data.append(rating_data)
            participant_ids.add(rating.rater_participant_id)

        current_time_millis = int(datetime.now(UTC).timestamp() * 1000)

        enrollment_data = [
            {
                participantIdKey: pid,
                enrollmentState: earnedIn,
                successfulRatingNeededToEarnIn: 0,
                timestampOfLastStateChange: current_time_millis,
                timestampOfLastEarnOut: None,
                modelingPopulationKey: core,
                modelingGroupKey: 0.0,
                numberOfTimesEarnedOutKey: 0,
            }
            for pid in participant_ids
        ]

        print(
            f"Prepared {len(notes_data)} notes, {len(ratings_data)} ratings, {len(status_data)} status records, {len(enrollment_data)} participants"
        )

        return notes_data, ratings_data, status_data, enrollment_data

    async def run_scoring(
        self,
        notes_data: list[dict],
        ratings_data: list[dict],
        status_data: list[dict],
        enrollment_data: list[dict],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        print("\nRunning scoring algorithm...")

        try:
            scored_notes, helpful_scores, aux_info = await self.scoring_adapter.score_notes(
                notes=notes_data,
                ratings=ratings_data,
                enrollment=enrollment_data,
                status=status_data,
            )

            print(f"Scoring complete: {len(scored_notes)} notes scored")
            self.validation_results["notes_scored"] = len(scored_notes)

            return scored_notes, helpful_scores, aux_info

        except Exception as e:
            error_msg = f"Scoring algorithm error: {e!s}"
            print(f"ERROR: {error_msg}")
            self.validation_results["errors"].append(error_msg)
            raise

    async def update_notes_with_scores(self, notes: list[Note], scored_notes: list[dict]) -> None:
        print("\nUpdating notes with scoring results...")

        note_id_to_note = {note.note_id: note for note in notes}
        status_before = Counter(note.status for note in notes)

        updates = 0

        for scored_note in scored_notes:
            note_id = scored_note.get("noteId")
            if note_id not in note_id_to_note:
                continue

            note = note_id_to_note[note_id]
            old_status = note.status

            if "currentStatus" in scored_note:
                new_status = scored_note["currentStatus"]
                note.status = new_status

                if old_status != new_status:
                    transition = f"{old_status} → {new_status}"
                    self.validation_results["status_transitions"][transition] = (
                        self.validation_results["status_transitions"].get(transition, 0) + 1
                    )

            if "coreNoteInterceptMin" in scored_note:
                note.helpfulness_score = int(scored_note["coreNoteInterceptMin"] * 100)

            updates += 1

        await self.session.commit()

        status_after = Counter(note.status for note in notes)

        print(f"Updated {updates} notes")
        print(f"\nStatus before: {dict(status_before)}")
        print(f"Status after:  {dict(status_after)}")

    def analyze_results(
        self, notes: list[Note], ratings: list[Rating], scored_notes: list[dict]
    ) -> None:
        print("\n" + "=" * 60)
        print("Scoring Analysis")
        print("=" * 60)

        scores = []
        for scored_note in scored_notes:
            if "coreNoteInterceptMin" in scored_note:
                scores.append(scored_note["coreNoteInterceptMin"])

        if scores:
            self.validation_results["score_distribution"] = {
                "min": min(scores),
                "max": max(scores),
                "mean": sum(scores) / len(scores),
                "count": len(scores),
            }

            print("\nScore Distribution:")
            print(f"  Min:  {min(scores):.4f}")
            print(f"  Max:  {max(scores):.4f}")
            print(f"  Mean: {sum(scores) / len(scores):.4f}")

        note_id_to_ratings = {}
        for rating in ratings:
            if rating.note_id not in note_id_to_ratings:
                note_id_to_ratings[rating.note_id] = []
            note_id_to_ratings[rating.note_id].append(rating)

        print("\nEdge Cases:")

        few_ratings_notes = [
            note for note in notes if len(note_id_to_ratings.get(note.note_id, [])) < 5
        ]
        if few_ratings_notes:
            print(f"  Notes with < 5 ratings: {len(few_ratings_notes)}")
            self.validation_results["edge_cases"].append(
                {"type": "few_ratings", "count": len(few_ratings_notes)}
            )

        all_positive_notes = [
            note
            for note in notes
            if all(
                r.helpfulness_level == "HELPFUL" for r in note_id_to_ratings.get(note.note_id, [])
            )
            and len(note_id_to_ratings.get(note.note_id, [])) > 0
        ]
        if all_positive_notes:
            print(f"  Notes with all HELPFUL ratings: {len(all_positive_notes)}")
            self.validation_results["edge_cases"].append(
                {"type": "all_positive", "count": len(all_positive_notes)}
            )

        all_negative_notes = [
            note
            for note in notes
            if all(
                r.helpfulness_level == "NOT_HELPFUL"
                for r in note_id_to_ratings.get(note.note_id, [])
            )
            and len(note_id_to_ratings.get(note.note_id, [])) > 0
        ]
        if all_negative_notes:
            print(f"  Notes with all NOT_HELPFUL ratings: {len(all_negative_notes)}")
            self.validation_results["edge_cases"].append(
                {"type": "all_negative", "count": len(all_negative_notes)}
            )

        polarizing_notes = [
            note
            for note in notes
            if note.status == "NEEDS_MORE_RATINGS"
            and len(note_id_to_ratings.get(note.note_id, [])) >= 10
        ]
        if polarizing_notes:
            print(
                f"  Polarizing notes (≥10 ratings, still NEEDS_MORE_RATINGS): {len(polarizing_notes)}"
            )
            self.validation_results["edge_cases"].append(
                {"type": "polarizing", "count": len(polarizing_notes)}
            )

        print("\nStatus Distribution:")
        status_counts = Counter(note.status for note in notes)
        for status, count in status_counts.items():
            print(f"  {status}: {count}")

    def generate_recommendations(self) -> None:
        print("\n" + "=" * 60)
        print("Recommendations")
        print("=" * 60)

        recommendations = []

        if self.validation_results["errors"]:
            recommendations.append("⚠️  Fix scoring errors before deploying to production")

        notes_scored = self.validation_results.get("notes_scored", 0)
        notes_processed = self.validation_results.get("notes_processed", 0)

        if notes_scored < notes_processed:
            recommendations.append(
                f"⚠️  Only {notes_scored}/{notes_processed} notes were scored - investigate missing notes"
            )

        if self.validation_results.get("score_distribution"):
            dist = self.validation_results["score_distribution"]
            if dist["min"] == dist["max"]:
                recommendations.append("⚠️  All scores are identical - check rating diversity")

        transitions = self.validation_results.get("status_transitions", {})
        if not transitions:
            recommendations.append("⚠️  No status transitions occurred - validate scoring logic")

        if not recommendations:
            recommendations.append("✅ Scoring algorithm working as expected")
            recommendations.append("✅ Ready for production use")

        self.validation_results["recommendations"] = recommendations

        for rec in recommendations:
            print(f"  {rec}")

    async def validate(self) -> dict:
        print("=" * 60)
        print("Scoring Validation Started")
        print("=" * 60)

        notes, ratings = await self.fetch_notes_and_ratings()

        if not notes:
            print("\n⚠️  No notes found in database. Run generate_test_data.py first.")
            return self.validation_results

        notes_data, ratings_data, status_data, enrollment_data = self.prepare_scoring_data(
            notes, ratings
        )

        scored_notes, _helpful_scores, _aux_info = await self.run_scoring(
            notes_data, ratings_data, status_data, enrollment_data
        )

        await self.update_notes_with_scores(notes, scored_notes)

        self.analyze_results(notes, ratings, scored_notes)

        self.generate_recommendations()

        print("\n" + "=" * 60)
        print("Validation Complete")
        print("=" * 60)

        return self.validation_results


async def main():
    print("\nOpen Notes Scoring Validation")
    print("=" * 60)
    print(f"Database URL: {settings.DATABASE_URL}")
    print("=" * 60)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        validator = ScoringValidator(session)
        results = await validator.validate()

        output_dir = Path(__file__).parent.parent / "docs"
        output_dir.mkdir(exist_ok=True)

        report_path = output_dir / "SCORING_VALIDATION_REPORT.json"
        with report_path.open("w") as f:
            json.dump(results, f, indent=2)

        print(f"\nValidation results saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
