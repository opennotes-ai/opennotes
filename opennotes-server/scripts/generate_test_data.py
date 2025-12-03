#!/usr/bin/env python3

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.models import Note, Rating, Request


class TestDataGenerator:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.participant_ids = []
        self.requests = []
        self.notes = []
        self.ratings = []
        self.random = random.Random(42)

    def _generate_participant_id(self, prefix: str, index: int) -> str:
        return f"{prefix}-{index:04d}-{self.random.randint(1000, 9999)}"

    def _generate_timestamp(self, days_ago: int) -> datetime:
        dt = datetime.now(UTC) - timedelta(days=days_ago)
        return dt.replace(tzinfo=None)

    async def generate_participants(self, count: int = 20) -> None:
        print(f"Generating {count} participant IDs...")

        self.participant_ids = [self._generate_participant_id("user", i) for i in range(count)]

        print(f"Generated {len(self.participant_ids)} participants")

    async def generate_requests(self, count: int = 50) -> None:
        print(f"\nGenerating {count} note requests...")

        base_message_id = 900000000000000000

        for i in range(count):
            days_ago = self.random.randint(1, 30)
            requester = self.random.choice(self.participant_ids)

            # Create MessageArchive first
            message_content = self._generate_message_content()
            platform_message_id = str(base_message_id + i)
            timestamp = self._generate_timestamp(days_ago)

            message_archive = MessageArchive(
                platform="discord",
                platform_message_id=platform_message_id,
                platform_channel_id=f"channel-{i % 5}",
                platform_author_id=f"author-{self.random.randint(1000, 9999)}",
                platform_timestamp=timestamp,
                content_type=ContentType.TEXT,
                text_content=message_content,
            )
            self.session.add(message_archive)
            await self.session.flush()

            request = Request(
                request_id=f"req-{i:04d}-{self.random.randint(1000, 9999)}",
                message_archive_id=message_archive.id,
                requested_by=requester,
                requested_at=timestamp,
                status="COMPLETED",
            )

            self.session.add(request)
            self.requests.append(request)

        await self.session.flush()
        print(f"Generated {len(self.requests)} requests")

    def _generate_message_content(self) -> str:
        topic_messages = [
            "New vaccine trials show promising results with 90% efficacy rate against new variants",
            "Study reveals connection between daily exercise and reduced risk of heart disease",
            "FDA approves groundbreaking medication for treatment of rare genetic disorder",
            "Global temperatures reach record highs as climate scientists warn of tipping points",
            "New carbon capture technology could reduce industrial emissions by 50 percent",
            "IPCC report highlights urgent need for renewable energy transition by 2030",
            "Latest AI model demonstrates human-level performance on complex reasoning tasks",
            "Cybersecurity experts warn about vulnerabilities in widely-used encryption protocols",
            "Tech companies announce new privacy standards following data breach concerns",
            "Economic data shows unemployment falling to lowest level in five years",
            "Federal Reserve announces interest rate decision amid inflation concerns",
            "New analysis reveals GDP growth exceeding expectations for third quarter",
            "Congress passes bipartisan infrastructure bill with environmental provisions",
            "New legislation aims to regulate social media platforms and protect user data",
            "Government agencies implement stricter regulations on corporate emissions",
            "Research team discovers potential breakthrough in renewable battery technology",
            "Peer-reviewed study questions previous findings on dietary supplement effectiveness",
            "Scientists identify new species in deep ocean expedition with advanced imaging",
            "Analysis of satellite data reveals previously unknown migration patterns",
            "Economic forecast predicts market volatility due to geopolitical tensions",
        ]

        return self.random.choice(topic_messages)

    async def generate_notes(self, count: int = 50) -> None:
        print(f"\nGenerating {count} notes...")

        base_note_id = 800000000000000000
        classifications = [("NOT_MISLEADING", 20), ("MISINFORMED_OR_POTENTIALLY_MISLEADING", 30)]

        note_types = {"helpful": 20, "unhelpful": 15, "polarizing": 10, "borderline": 5}

        note_index = 0

        for note_type, type_count in note_types.items():
            for _i in range(type_count):
                if note_index >= count:
                    break

                request = self.requests[note_index]
                author = self.random.choice(
                    [p for p in self.participant_ids if p != request.requested_by]
                )

                classification_weights = [c[1] for c in classifications]
                classification = self.random.choices(
                    [c[0] for c in classifications], weights=classification_weights
                )[0]

                note = Note(
                    note_id=base_note_id + note_index,
                    author_participant_id=author,
                    request_id=request.request_id,
                    summary=self._generate_note_summary(note_type, classification),
                    classification=classification,
                    helpfulness_score=0,
                    status="NEEDS_MORE_RATINGS",
                )

                self.session.add(note)
                self.notes.append((note, note_type))
                note_index += 1

        await self.session.flush()
        print(f"Generated {len(self.notes)} notes")

    def _generate_note_summary(self, note_type: str, classification: str) -> str:  # noqa: ARG002
        topic_group = self.random.randint(0, 2)

        if topic_group == 0:
            if classification == "NOT_MISLEADING":
                templates = [
                    "The statistical analysis methodology used in this research follows established scientific protocols and has been peer-reviewed by independent experts in the field.",
                    "Multiple universities have replicated these experimental findings using controlled laboratory conditions with consistent results across different research teams.",
                    "This conclusion is supported by comprehensive data collection spanning multiple years with rigorous quality control measures throughout the study period.",
                ]
            else:
                templates = [
                    "The statistical methodology referenced here does not follow standard scientific protocols and lacks independent verification from qualified researchers.",
                    "Attempts to replicate these experimental claims in controlled laboratory settings have failed to produce consistent results.",
                    "This conclusion is not supported by comprehensive data analysis and appears to cherry-pick findings without proper quality controls.",
                ]
        elif topic_group == 1:
            if classification == "NOT_MISLEADING":
                templates = [
                    "Economic indicators from the Federal Reserve clearly demonstrate this trend, with quarterly reports showing consistent patterns over the past fiscal year.",
                    "Market analysts at major financial institutions have documented these developments through detailed portfolio analysis and risk assessment models.",
                    "The reported economic growth figures align with official government statistics published by the Bureau of Economic Analysis and Treasury Department.",
                ]
            else:
                templates = [
                    "Economic indicators from reputable institutions do not support this claim, and quarterly reports show contradictory patterns in market behavior.",
                    "Financial analysts have been unable to verify these developments, and detailed portfolio analysis reveals inconsistencies in the reported figures.",
                    "The economic growth claims do not match official government statistics and appear to misrepresent data from the Bureau of Economic Analysis.",
                ]
        elif classification == "NOT_MISLEADING":
            templates = [
                "Public health authorities have confirmed these medical findings through extensive clinical trials involving thousands of participants across multiple countries.",
                "The treatment protocol described follows FDA-approved guidelines and is based on randomized controlled trials published in peer-reviewed medical journals.",
                "Healthcare professionals across numerous hospitals have documented similar patient outcomes using standardized diagnostic criteria and follow-up procedures.",
            ]
        else:
            templates = [
                "Public health authorities have not verified these medical claims, and clinical trial data does not support the described outcomes for patient treatment.",
                "This treatment approach contradicts FDA-approved guidelines and lacks support from randomized controlled trials in reputable medical literature.",
                "Healthcare professionals report different patient outcomes than claimed here, based on standardized diagnostic protocols and documented follow-up studies.",
            ]

        return self.random.choice(templates)

    async def generate_ratings(self) -> None:
        print(f"\nGenerating ratings for {len(self.notes)} notes...")

        rating_patterns = {
            "helpful": (15, 20, [("HELPFUL", 80), ("SOMEWHAT_HELPFUL", 15), ("NOT_HELPFUL", 5)]),
            "unhelpful": (12, 18, [("NOT_HELPFUL", 70), ("SOMEWHAT_HELPFUL", 20), ("HELPFUL", 10)]),
            "polarizing": (
                10,
                20,
                [("HELPFUL", 45), ("SOMEWHAT_HELPFUL", 10), ("NOT_HELPFUL", 45)],
            ),
            "borderline": (5, 8, [("HELPFUL", 40), ("SOMEWHAT_HELPFUL", 30), ("NOT_HELPFUL", 30)]),
        }

        total_ratings = 0

        for note, note_type in self.notes:
            min_ratings, max_ratings, helpfulness_dist = rating_patterns[note_type]
            num_ratings = self.random.randint(min_ratings, max_ratings)

            available_raters = [p for p in self.participant_ids if p != note.author_participant_id]

            num_ratings = min(len(available_raters), num_ratings)

            selected_raters = self.random.sample(available_raters, num_ratings)

            helpfulness_levels = [h[0] for h in helpfulness_dist]
            helpfulness_weights = [h[1] for h in helpfulness_dist]

            for rater in selected_raters:
                helpfulness = self.random.choices(helpfulness_levels, weights=helpfulness_weights)[
                    0
                ]

                rating = Rating(
                    rater_participant_id=rater, note_id=note.note_id, helpfulness_level=helpfulness
                )

                self.session.add(rating)
                self.ratings.append(rating)
                total_ratings += 1

        await self.session.flush()
        print(f"Generated {total_ratings} ratings across all notes")

    async def generate_all(self) -> None:
        print("=" * 60)
        print("Test Data Generation Started")
        print("=" * 60)

        await self.generate_participants(20)
        await self.generate_requests(50)
        await self.generate_notes(50)
        await self.generate_ratings()

        await self.session.commit()

        print("\n" + "=" * 60)
        print("Test Data Generation Complete")
        print("=" * 60)
        print("\nSummary:")
        print(f"  Participants: {len(self.participant_ids)}")
        print(f"  Requests: {len(self.requests)}")
        print(f"  Notes: {len(self.notes)}")
        print(f"  Ratings: {len(self.ratings)}")

    async def display_statistics(self) -> None:
        print("\n" + "=" * 60)
        print("Database Statistics")
        print("=" * 60)

        result = await self.session.execute(select(Request))
        requests_count = len(result.scalars().all())

        result = await self.session.execute(select(Note))
        notes = result.scalars().all()
        notes_count = len(notes)

        result = await self.session.execute(select(Rating))
        ratings_count = len(result.scalars().all())

        print("\nTotal Records:")
        print(f"  Requests: {requests_count}")
        print(f"  Notes: {notes_count}")
        print(f"  Ratings: {ratings_count}")

        if notes:
            print("\nNote Classifications:")
            not_misleading = sum(1 for n in notes if n.classification == "NOT_MISLEADING")
            misleading = sum(
                1 for n in notes if n.classification == "MISINFORMED_OR_POTENTIALLY_MISLEADING"
            )
            print(f"  NOT_MISLEADING: {not_misleading}")
            print(f"  MISINFORMED_OR_POTENTIALLY_MISLEADING: {misleading}")

            print("\nNote Status:")
            status_counts = {}
            for note in notes:
                status_counts[note.status] = status_counts.get(note.status, 0) + 1
            for status, count in status_counts.items():
                print(f"  {status}: {count}")


async def clear_existing_data(session: AsyncSession) -> None:
    print("\nClearing existing test data...")

    result = await session.execute(select(Note))
    notes_before = len(result.scalars().all())

    result = await session.execute(select(Rating))
    ratings_before = len(result.scalars().all())

    result = await session.execute(select(Request))
    requests_before = len(result.scalars().all())

    result = await session.execute(select(MessageArchive))
    archives_before = len(result.scalars().all())

    await session.execute(Rating.__table__.delete())
    await session.execute(Note.__table__.delete())
    await session.execute(Request.__table__.delete())
    await session.execute(MessageArchive.__table__.delete())

    await session.commit()

    print(
        f"Cleared {ratings_before} ratings, {notes_before} notes, "
        f"{requests_before} requests, {archives_before} message archives"
    )


async def main():
    print("\nOpen Notes Test Data Generator")
    print("=" * 60)
    print(f"Database URL: {settings.DATABASE_URL}")
    print("=" * 60)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        await clear_existing_data(session)

        generator = TestDataGenerator(session)
        await generator.generate_all()
        await generator.display_statistics()


if __name__ == "__main__":
    asyncio.run(main())
