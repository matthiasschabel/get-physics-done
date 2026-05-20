"""HTML retrieval for arxiv papers via ar5iv.labs.arxiv.org."""

from __future__ import annotations

import logging
from html.parser import HTMLParser

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


def fetch_html_content(paper_id: str) -> str | None:
    # ar5iv first (follow_redirects=False so 307 = miss, not a hop into
    # arxiv.org). arxiv.org/html as fallback for papers ar5iv lacks.
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
                    continue

                text = _html_to_text(resp.text)
                if text.strip():
                    return text
    except Exception:
        logger.exception("unexpected error in HTML fetch for %s", paper_id)
    return None
