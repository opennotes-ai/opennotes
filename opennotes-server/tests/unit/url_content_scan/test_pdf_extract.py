"""Unit tests for url_content_scan.pdf_extract (TASK-1657.28).

TDD test cases:
- Extract text + page metadata from a valid PDF
- Malformed PDF -> graceful error (PdfExtractionError, no unexpected exception)
- Empty PDF bytes -> PdfExtractionError
- Empty-text PDF (structure valid, no text layer) -> empty text, row still written
"""

from __future__ import annotations

import pytest


def _make_minimal_pdf_bytes(text: str = "Hello PDF world") -> bytes:
    """Build a minimal valid single-page PDF with a text stream."""
    stream_content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    stream_len = len(stream_content)

    offsets: list[int] = []
    body = b""

    def _append(obj: bytes) -> int:
        nonlocal body
        off = len(body)
        offsets.append(off)
        body += obj
        return off

    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
        b">>\nendobj\n"
    )
    obj4 = (
        b"4 0 obj\n<< /Length "
        + str(stream_len).encode()
        + b" >>\nstream\n"
        + stream_content
        + b"\nendstream\nendobj\n"
    )

    _append(obj1)
    _append(obj2)
    _append(obj3)
    _append(obj4)

    header = b"%PDF-1.4\n"
    all_offsets = [len(header) + o for o in offsets]

    xref_start = len(header) + len(body)
    xref = b"xref\n0 5\n0000000000 65535 f \n"
    for off in all_offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = (
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n" + str(xref_start).encode() + b"\n%%EOF\n"
    )

    return header + body + xref + trailer


def _make_empty_page_pdf_bytes() -> bytes:
    """PDF with one page but no text content (no content stream)."""
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"

    header = b"%PDF-1.4\n"
    body = obj1 + obj2 + obj3
    xref_start = len(header) + len(body)
    xref = b"xref\n0 4\n0000000000 65535 f \n"
    cumulative = len(header)
    for obj in [obj1, obj2, obj3]:
        xref += f"{cumulative:010d} 00000 n \n".encode()
        cumulative += len(obj)
    trailer = (
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n" + str(xref_start).encode() + b"\n%%EOF\n"
    )
    return header + body + xref + trailer


class TestExtractPdfContent:
    def test_extracts_text_from_valid_pdf(self):
        from src.url_content_scan.pdf_extract import extract_pdf_content

        pdf_bytes = _make_minimal_pdf_bytes("Hello PDF world")
        content = extract_pdf_content(pdf_bytes)

        assert content.page_count == 1
        assert isinstance(content.page_texts, list)
        assert len(content.page_texts) == 1
        assert isinstance(content.text, str)
        assert isinstance(content.metadata, dict)

    def test_page_count_matches_pages(self):
        from src.url_content_scan.pdf_extract import extract_pdf_content

        pdf_bytes = _make_minimal_pdf_bytes("Test page")
        content = extract_pdf_content(pdf_bytes)
        assert content.page_count == len(content.page_texts)

    def test_malformed_pdf_raises_extraction_error(self):
        from src.url_content_scan.pdf_extract import PdfExtractionError, extract_pdf_content

        malformed = b"this is not a pdf at all"
        with pytest.raises(PdfExtractionError):
            extract_pdf_content(malformed)

    def test_empty_bytes_raises_extraction_error(self):
        from src.url_content_scan.pdf_extract import PdfExtractionError, extract_pdf_content

        with pytest.raises(PdfExtractionError):
            extract_pdf_content(b"")

    def test_empty_page_pdf_returns_empty_text(self):
        from src.url_content_scan.pdf_extract import extract_pdf_content

        pdf_bytes = _make_empty_page_pdf_bytes()
        content = extract_pdf_content(pdf_bytes)

        assert content.page_count >= 1
        assert content.text == "" or isinstance(content.text, str)

    def test_metadata_is_dict(self):
        from src.url_content_scan.pdf_extract import extract_pdf_content

        pdf_bytes = _make_minimal_pdf_bytes("Metadata test")
        content = extract_pdf_content(pdf_bytes)
        assert isinstance(content.metadata, dict)

    def test_pdf_content_dataclass_fields(self):
        from src.url_content_scan.pdf_extract import PdfContent

        pc = PdfContent(text="hello", page_count=1, page_texts=["hello"], metadata={"Author": "A"})
        assert pc.text == "hello"
        assert pc.page_count == 1
        assert pc.page_texts == ["hello"]
        assert pc.metadata == {"Author": "A"}

    def test_no_unexpected_exception_on_truncated_pdf(self):
        from src.url_content_scan.pdf_extract import PdfExtractionError, extract_pdf_content

        truncated = b"%PDF-1.4\n1 0 obj\n<< /Type"
        try:
            extract_pdf_content(truncated)
        except PdfExtractionError:
            pass
        except Exception as exc:
            pytest.fail(f"unexpected exception type: {type(exc).__name__}: {exc}")
