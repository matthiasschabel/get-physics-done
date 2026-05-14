"""HTML retrieval for arxiv papers via ar5iv.labs.arxiv.org.

ar5iv is arxiv's own LaTeXML-based HTML rendering service. It sits on a
separate origin from arxiv.org (different rate-limit budget, confirmed
by live probe: 20 sequential requests with no 429s) and covers ~100% of
real arxiv IDs in our sample. The HTML is class-compatible with the
arxiv.org/html output that ``arxiv_mcp_server.tools.download._html_to_text``
already parses.

Primary use: replace ``arxiv.org/html/{id}`` as the first fetch path in
``arxiv_bridge.download_paper``. ar5iv 307-redirects when a paper isn't
in its corpus (e.g. very recent submissions); we treat that as a miss
rather than following the redirect, so the next fallback layer fires.
"""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from typing import Optional

import httpx

from gpd.version import __version__ as GPD_VERSION

logger = logging.getLogger("gpd.arxiv_bridge.ar5iv")

_AR5IV_BASE = "https://ar5iv.labs.arxiv.org/html"
_ARXIV_HTML_BASE = "https://arxiv.org/html"

_USER_AGENT = (
    f"gpd-arxiv-bridge/{GPD_VERSION} "
    "(+https://github.com/psi-oss/get-physics-done; mailto:ops@psi.inc)"
)
_HEADERS = {"User-Agent": _USER_AGENT}
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class _ArticleTextExtractor(HTMLParser):
    """Plain-text extractor mirroring ``arxiv_mcp_server.tools.download._ArticleTextExtractor``.

    Skips script/style/nav/header/footer/aside subtrees and joins the
    remaining stripped text chunks with newlines. Identical output shape
    to the upstream extractor so the downstream content envelope stays
    compatible with cache reads and read_paper.
    """

    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth: int = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._chunks)


def _html_to_text(html: str) -> str:
    parser = _ArticleTextExtractor()
    parser.feed(html)
    return parser.get_text()


def fetch_html_content(paper_id: str) -> Optional[str]:
    """Fetch a paper's HTML and return its extracted plain text.

    Order:
      1. ``ar5iv.labs.arxiv.org/html/{paper_id}`` with ``follow_redirects=False``.
         A 307 redirect means ar5iv doesn't have the paper (typically very
         recent submissions); treat as miss without leaking a hop into
         ar5iv's logs.
      2. ``arxiv.org/html/{paper_id}`` with ``follow_redirects=True``.
         Last HTML option before the PDF path.

    Returns the extracted text on the first 200 with non-empty body. Returns
    ``None`` if both endpoints miss, so the caller can fall through to the
    PDF path. Never raises on network errors — they are logged and treated
    as misses (same convention as upstream ``_fetch_html_content``).
    """
    attempts = (
        (_AR5IV_BASE, False, "ar5iv"),
        (_ARXIV_HTML_BASE, True, "arxiv-html"),
    )
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for base, follow, label in attempts:
                url = f"{base}/{paper_id}"
                try:
                    resp = client.get(url, follow_redirects=follow)
                except httpx.RequestError as exc:
                    logger.info("html-%s request error for %s: %s", label, paper_id, exc)
                    continue

                if resp.status_code != 200:
                    logger.info(
                        "html-%s miss for %s: status=%d",
                        label,
                        paper_id,
                        resp.status_code,
                    )
                    continue

                if not resp.content:
                    logger.info("html-%s empty body for %s", label, paper_id)
                    continue

                text = _html_to_text(resp.text)
                if text.strip():
                    logger.info(
                        "html-%s hit for %s (%d bytes html -> %d chars text)",
                        label,
                        paper_id,
                        len(resp.content),
                        len(text),
                    )
                    return text

                logger.info("html-%s extracted empty text for %s", label, paper_id)
    except Exception:
        logger.exception("unexpected error in HTML fetch for %s", paper_id)
    return None
