"""PDF retrieval for arxiv papers via the public Cornell-Google GCS bucket."""

from __future__ import annotations

import gc
import logging
import re
import tempfile
import unicodedata
from pathlib import Path

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

_NEW_RE = re.compile(r"^(?P<yymm>\d{4})\.(?P<num>\d{4,5})(?:v\d+)?$")
_OLD_RE = re.compile(
    r"^(?P<cat>[a-z][a-z0-9\-]*(?:\.[a-z][a-z0-9\-]*)?)/(?P<yymm>\d{4})(?P<num>\d{3,})(?:v\d+)?$"
)


def parse_paper_id(paper_id: str) -> tuple[str, str, str]:
    """Parse an arXiv identifier into ``(gcs_prefix, yymm, stem)``.

    ``2103.15556[vN]`` → ``("arxiv", "2103", "2103.15556")``.
    ``hep-th/9901001[vN]`` → ``("hep-th", "9901", "9901001")`` — numeric
    tail only; ``hep-th9901001`` etc. 404 on the bucket.
    """
    if not isinstance(paper_id, str):
        raise ValueError(f"paper_id must be a string, got {type(paper_id).__name__}")

    s = unicodedata.normalize("NFKC", paper_id).strip()
    if s.lower().endswith(".pdf"):
        s = s[:-4]
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


def fetch_pdf_from_gcs(paper_id: str) -> bytes | None:
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
                    continue

                try:
                    resp = client.get(url)
                except httpx.RequestError as exc:
                    logger.info("gcs GET error %s v%d: %s", paper_id, v, exc)
                    continue

                if resp.status_code == 200 and resp.content:
                    return resp.content

                continue
    except Exception:
        logger.exception("unexpected error probing GCS for %s", paper_id)
    return None


def fetch_pdf_from_arxiv(paper_id: str) -> bytes | None:
    url = f"{_ARXIV_PDF_BASE}/{paper_id}.pdf"
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
            resp = client.get(url, follow_redirects=True)
    except httpx.RequestError as exc:
        logger.info("arxiv.org/pdf request error for %s: %s", paper_id, exc)
        return None

    if resp.status_code != 200:
        return None

    ct = resp.headers.get("content-type", "")
    if not ct.startswith("application/pdf"):
        return None

    return resp.content


def pdf_bytes_to_markdown(
    pdf_bytes: bytes, paper_id: str, storage_path: Path
) -> str:
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
    tmp_pdf: Path | None = None
    try:
        # Unique per-call temp file so concurrent conversions of the same paper
        # cannot delete or overwrite each other mid-pymupdf4llm.
        with tempfile.NamedTemporaryFile(
            dir=str(storage_path),
            prefix=f"{safe_id}.",
            suffix=".pdf",
            delete=False,
        ) as fh:
            fh.write(pdf_bytes)
            tmp_pdf = Path(fh.name)
        markdown = pymupdf4llm.to_markdown(str(tmp_pdf), show_progress=False)
    finally:
        gc.collect()
        if tmp_pdf is not None:
            try:
                tmp_pdf.unlink()
            except OSError:
                pass

    if not markdown or not markdown.strip():
        raise RuntimeError(f"PDF conversion produced empty output for {paper_id}")
    return markdown
