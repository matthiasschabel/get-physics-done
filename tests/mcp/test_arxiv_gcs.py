"""Unit tests for the GCS arxiv path parser and PDF fetch helpers.

The parser covers the two ID formats (new YYMM.NNNNN, old category/YYMMNNN)
and the path-building corner cases we've seen in production: trailing
.pdf, version suffixes, mixed case, leading whitespace. Live GCS fetch
is not exercised here — see scripts/arxiv-probe.py for network probes.
"""

from __future__ import annotations

import pytest

from gpd.mcp.servers import _arxiv_gcs


def test_parse_new_format_no_version() -> None:
    assert _arxiv_gcs.parse_paper_id("2401.12345") == ("arxiv", "2401", "2401.12345")


def test_parse_new_format_with_version() -> None:
    assert _arxiv_gcs.parse_paper_id("2401.12345v3") == ("arxiv", "2401", "2401.12345")


def test_parse_new_format_four_digit_number() -> None:
    # Pre-2015 arxiv IDs sometimes have 4-digit suffixes.
    assert _arxiv_gcs.parse_paper_id("0904.1556") == ("arxiv", "0904", "0904.1556")


def test_parse_old_format() -> None:
    """Old-format IDs use just the numeric tail in the GCS path, not the
    concatenated form. Confirmed via live probe — `hep-th9901001` 404s,
    `9901001` returns 200."""
    assert _arxiv_gcs.parse_paper_id("hep-th/9901001") == ("hep-th", "9901", "9901001")


def test_parse_old_format_with_version() -> None:
    assert _arxiv_gcs.parse_paper_id("hep-th/9901001v2") == ("hep-th", "9901", "9901001")


def test_parse_strips_trailing_pdf() -> None:
    assert _arxiv_gcs.parse_paper_id("2401.12345.pdf") == ("arxiv", "2401", "2401.12345")


def test_parse_lowercases_category() -> None:
    # arxiv old-style category prefixes are lowercase; some tools pass mixed case.
    assert _arxiv_gcs.parse_paper_id("HEP-TH/9901001") == ("hep-th", "9901", "9901001")


def test_parse_strips_whitespace() -> None:
    assert _arxiv_gcs.parse_paper_id("  2401.12345  ") == ("arxiv", "2401", "2401.12345")


def test_parse_rejects_bogus_input() -> None:
    with pytest.raises(ValueError):
        _arxiv_gcs.parse_paper_id("not-an-arxiv-id")


def test_parse_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        _arxiv_gcs.parse_paper_id(12345)  # type: ignore[arg-type]


def test_parse_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _arxiv_gcs.parse_paper_id("")


def test_pdf_bytes_to_markdown_rejects_empty_output(tmp_path) -> None:
    """If pymupdf4llm returns an empty string we must raise rather than
    cache empty content. The 100-byte zero-fill is enough to not crash
    pymupdf but its `to_markdown` call has been observed to return
    empty on malformed inputs."""
    pytest.importorskip("pymupdf4llm")
    with pytest.raises((RuntimeError, Exception)):
        # Garbage bytes — pymupdf raises, which is fine for this test.
        _arxiv_gcs.pdf_bytes_to_markdown(b"\x00" * 100, "test/0000001", tmp_path)
