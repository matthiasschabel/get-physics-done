"""PDF retrieval for arxiv papers via the public Cornell-Google GCS bucket.

``gs://arxiv-dataset`` is a public, anonymous-read mirror of the entire
arxiv PDF corpus, referenced by arxiv staff in the arxiv-api Google
group as a sanctioned bulk channel. Layout:

- New-format IDs (``YYMM.NNNNN``):
  ``arxiv/arxiv/pdf/{yymm}/{paper_id}v{N}.pdf``
- Old-format IDs (``category/YYMMNNN``, e.g. ``hep-th/9901001``):
  ``arxiv/{category}/pdf/{yymm}/{numeric}v{N}.pdf``
  (note: numeric tail only — concatenated forms like ``hep-th9901001`` 404)

This module is the PDF fallback in ``arxiv_bridge.download_paper`` when
ar5iv HTML is unavailable. It avoids hitting ``arxiv.org/pdf/{id}``
directly because that endpoint shares the same per-IP rate-limit budget
as the rest of arxiv.org.
"""

from __future__ import annotations

import gc
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

import httpx

from gpd.version import __version__ as GPD_VERSION

logger = logging.getLogger("gpd.arxiv_bridge.gcs")

_GCS_BASE = "https://storage.googleapis.com/arxiv-dataset/arxiv"
_ARXIV_PDF_BASE = "https://arxiv.org/pdf"

_USER_AGENT = (
    f"gpd-arxiv-bridge/{GPD_VERSION} "
    "(+https://github.com/psi-oss/get-physics-done; mailto:ops@psi.inc)"
)
_HEADERS = {"User-Agent": _USER_AGENT}
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# New-format arXiv ID: YYMM.NNNNN  with optional vN
_NEW_RE = re.compile(r"^(?P<yymm>\d{4})\.(?P<num>\d{4,5})(?:v\d+)?$")
# Old-format arXiv ID: category/YYMMNNN  with optional vN (NNN = 3+ digits)
_OLD_RE = re.compile(
    r"^(?P<cat>[a-z][a-z0-9\-]*(?:\.[A-Z]{2})?)/(?P<yymm>\d{4})(?P<num>\d{3,})(?:v\d+)?$"
)


def parse_paper_id(paper_id: str) -> tuple[str, str, str]:
    """Parse an arXiv identifier into ``(gcs_prefix, yymm, stem)``.

    - New format ``"2103.15556"`` (with or without ``v2``)
      → ``("arxiv", "2103", "2103.15556")``
    - Old format ``"hep-th/9901001"`` (with or without ``v2``)
      → ``("hep-th", "9901", "9901001")``

    The returned tuple plugs directly into the GCS path
    ``arxiv/{prefix}/pdf/{yymm}/{stem}v{N}.pdf``.

    Raises ``ValueError`` for any input that doesn't match either
    canonical arXiv ID format.
    """
    if not isinstance(paper_id, str):
        raise ValueError(f"paper_id must be a string, got {type(paper_id).__name__}")

    s = unicodedata.normalize("NFKC", paper_id).strip()
    if s.lower().endswith(".pdf"):
        s = s[:-4]
    # Lowercase only the category portion (everything before the slash).
    if "/" in s:
        cat, _, rest = s.partition("/")
        s = f"{cat.lower()}/{rest}"

    m = _NEW_RE.match(s)
    if m:
        return ("arxiv", m["yymm"], f"{m['yymm']}.{m['num']}")

    m = _OLD_RE.match(s)
    if m:
        return (m["cat"], m["yymm"], f"{m['yymm']}{m['num']}")

    raise ValueError(f"Unrecognised arXiv identifier: {paper_id!r}")


def fetch_pdf_from_gcs(paper_id: str) -> Optional[bytes]:
    """HEAD-probe versioned objects in ``gs://arxiv-dataset`` newest→oldest, then GET.

    Probes ``v3``, then ``v2``, then ``v1``. Returns the raw PDF bytes on
    first 200 GET. Returns ``None`` on any miss, parse failure, or network
    error — caller is expected to fall through to ``fetch_pdf_from_arxiv``.

    The HEAD→GET split is intentional: HEAD lets us cheaply probe N
    versions before pulling megabytes, and pre-HEAD detection means we
    don't waste an aborted GET on the wrong version.
    """
    try:
        prefix, yymm, stem = parse_paper_id(paper_id)
    except ValueError as exc:
        logger.info("cannot parse paper id %r for GCS: %s", paper_id, exc)
        return None

    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for v in (3, 2, 1):
                url = f"{_GCS_BASE}/{prefix}/pdf/{yymm}/{stem}v{v}.pdf"
                try:
                    head = client.head(url)
                except httpx.RequestError as exc:
                    logger.info("gcs HEAD error %s v%d: %s", paper_id, v, exc)
                    continue

                if head.status_code == 404:
                    continue

                if head.status_code != 200:
                    logger.info(
                        "gcs HEAD non-2xx for %s v%d: status=%d",
                        paper_id,
                        v,
                        head.status_code,
                    )
                    continue

                try:
                    resp = client.get(url)
                except httpx.RequestError as exc:
                    logger.info("gcs GET error %s v%d: %s", paper_id, v, exc)
                    return None

                if resp.status_code == 200 and resp.content:
                    logger.info(
                        "gcs hit %s v%d (%d bytes)", paper_id, v, len(resp.content)
                    )
                    return resp.content

                logger.info(
                    "gcs HEAD 200 but GET %d for %s v%d",
                    resp.status_code,
                    paper_id,
                    v,
                )
                return None
    except Exception:
        logger.exception("unexpected error probing GCS for %s", paper_id)
    return None


def fetch_pdf_from_arxiv(paper_id: str) -> Optional[bytes]:
    """Last-resort direct fetch from ``arxiv.org/pdf/{paper_id}.pdf``.

    Used when GCS misses (typically very recent papers not yet mirrored).
    Counts against arxiv.org's per-IP rate-limit budget, so callers must
    serialize through the arxiv token bucket before invoking this.

    Returns the raw PDF bytes on success, ``None`` on miss/error.
    """
    url = f"{_ARXIV_PDF_BASE}/{paper_id}.pdf"
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
            resp = client.get(url, follow_redirects=True)
    except httpx.RequestError as exc:
        logger.info("arxiv.org/pdf request error for %s: %s", paper_id, exc)
        return None

    if resp.status_code != 200:
        logger.info(
            "arxiv.org/pdf miss for %s: status=%d", paper_id, resp.status_code
        )
        return None

    ct = resp.headers.get("content-type", "")
    if not ct.startswith("application/pdf"):
        logger.info(
            "arxiv.org/pdf returned non-PDF content-type for %s: %s", paper_id, ct
        )
        return None

    return resp.content


def pdf_bytes_to_markdown(
    pdf_bytes: bytes, paper_id: str, storage_path: Path
) -> str:
    """Convert raw PDF bytes to Markdown via ``pymupdf4llm``.

    Writes the bytes to a temp file under ``storage_path`` (pymupdf4llm
    requires a path, not a buffer), runs ``to_markdown``, then deletes
    the temp file. Raises ``ImportError`` if the ``[pdf]`` extra of
    ``arxiv-mcp-server`` isn't installed — caller surfaces that as a
    tool-error envelope. Raises ``RuntimeError`` on empty conversion
    output.
    """
    try:
        import fitz
        import pymupdf4llm
    except ImportError as exc:
        raise ImportError(
            "PDF conversion requires pymupdf4llm. "
            "Install with: pip install 'arxiv-mcp-server[pdf]'"
        ) from exc

    try:
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass

    storage_path.mkdir(parents=True, exist_ok=True)
    safe_id = paper_id.replace("/", "_")
    tmp_pdf = storage_path / f"{safe_id}.pdf.tmp"
    try:
        tmp_pdf.write_bytes(pdf_bytes)
        markdown = pymupdf4llm.to_markdown(str(tmp_pdf), show_progress=False)
    finally:
        gc.collect()
        try:
            tmp_pdf.unlink()
        except OSError:
            pass

    if not markdown or not markdown.strip():
        raise RuntimeError(f"PDF conversion produced empty output for {paper_id}")
    return markdown
