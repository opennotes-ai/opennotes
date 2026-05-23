from enum import Enum


class ErrorCode(str, Enum):
    EXTRACTION_FAILED = "extraction_failed"
    INTERNAL = "internal"
    INVALID_URL = "invalid_url"
    RATE_LIMITED = "rate_limited"
    SECTION_FAILURE = "section_failure"
    TIMEOUT = "timeout"
    UNSAFE_URL = "unsafe_url"
    UNSUPPORTED_SITE = "unsupported_site"
    UPSTREAM_ERROR = "upstream_error"

    def __str__(self) -> str:
        return str(self.value)
