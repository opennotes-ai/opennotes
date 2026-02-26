from enum import Enum


class CandidateStatus(str, Enum):
    PENDING = "pending"
    PROMOTED = "promoted"
    PROMOTING = "promoting"
    SCRAPED = "scraped"
    SCRAPE_FAILED = "scrape_failed"
    SCRAPING = "scraping"

    def __str__(self) -> str:
        return str(self.value)
