"""PDF text and page-metadata extraction for url_scan.

Ports the extraction concern from vibecheck's pdf_extract.py into the
opennotes-server url_scan module.  Whereas vibecheck delegates to Firecrawl,
this module uses pypdf to extract structured text + per-page metadata directly
from the PDF bytes produced by the image-conversion workflow (or uploaded PDFs).

Public surface
--------------
extract_pdf_content(pdf_bytes)
    Parses a PDF from bytes and returns a PdfContent dataclass with:
    - ``text``        — concatenated text from all pages (may be empty)
    - ``page_count``  — total number of pages
    - ``page_texts``  — per-page text strings
    - ``metadata``    — dict with document-level PDF metadata (author, title, …)
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pypdf

from src.monitoring import get_logger

logger = get_logger(__name__)


class PdfExtractionError(Exception):
    """Raised when a PDF cannot be parsed at all (malformed / encrypted)."""


@dataclass
class PdfContent:
    text: str
    page_count: int
    page_texts: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def extract_pdf_content(pdf_bytes: bytes) -> PdfContent:
    """Extract text and metadata from *pdf_bytes*.

    Returns a :class:`PdfContent` instance.  An empty or text-free PDF returns
    an instance with ``text=""`` and ``page_texts=[]`` — callers must never
    raise on empty extraction; the archive row is still written.

    Raises :class:`PdfExtractionError` only when pypdf cannot parse the PDF
    header at all (i.e. the bytes are not a valid PDF container).
    """
    if not pdf_bytes:
        raise PdfExtractionError("empty PDF bytes")

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise PdfExtractionError(f"malformed PDF: {exc}") from exc

    page_count = len(reader.pages)
    page_texts: list[str] = []

    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("pdf page text extraction failed: %s", exc)
            page_text = ""
        page_texts.append(page_text)

    full_text = "\n".join(page_texts).strip()

    raw_meta = reader.metadata or {}
    metadata: dict[str, object] = {}
    for key, value in raw_meta.items():
        str_key = str(key).lstrip("/")
        try:
            metadata[str_key] = str(value)
        except Exception:
            pass

    return PdfContent(
        text=full_text,
        page_count=page_count,
        page_texts=page_texts,
        metadata=metadata,
    )
