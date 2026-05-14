"""Unit tests for ar5iv HTML fetcher.

Live network calls are out of scope here — those live in
``scripts/arxiv-probe.py``. These tests cover the local extraction logic
and the fetch decision tree (ar5iv → arxiv.org/html fallback, 307-as-miss).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gpd.mcp.servers import _arxiv_ar5iv


def test_html_to_text_strips_script_style_nav() -> None:
    html = """
    <html>
      <head><script>alert('x')</script><style>body {}</style></head>
      <body>
        <nav>menu</nav>
        <header>top</header>
        <main>actual content</main>
        <footer>bottom</footer>
        <aside>side</aside>
      </body>
    </html>
    """
    text = _arxiv_ar5iv._html_to_text(html)
    # The extractor strips SKIP_TAGS — none of these should appear:
    for unwanted in ("alert", "menu", "top", "bottom", "side", "body {}"):
        assert unwanted not in text
    assert "actual content" in text


def test_html_to_text_returns_stripped_chunks() -> None:
    html = "<p>  hello   </p><p>world</p>"
    text = _arxiv_ar5iv._html_to_text(html)
    assert "hello" in text
    assert "world" in text


def _make_fake_client(responses: list[Any]) -> Any:
    """Build a context-manager-style httpx.Client mock that returns the
    given response objects in order on get()."""

    class FakeClient:
        def __init__(self) -> None:
            self._idx = 0

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *exc) -> None:
            pass

        def get(self, url: str, follow_redirects: bool = True) -> Any:
            resp = responses[self._idx]
            self._idx += 1
            return resp

    return FakeClient()


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


def test_fetch_hits_ar5iv_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ar5iv returns 200 with extractable text, the fallback is never tried."""
    fake = _make_fake_client(
        [_FakeResponse(200, content=b"<html><body>hello</body></html>", text="<html><body>hello</body></html>")]
    )

    def fake_client_ctor(*args, **kwargs) -> Any:
        return fake

    monkeypatch.setattr(_arxiv_ar5iv.httpx, "Client", fake_client_ctor)
    result = _arxiv_ar5iv.fetch_html_content("2401.00001")
    assert result is not None
    assert "hello" in result


def test_fetch_falls_through_on_307(monkeypatch: pytest.MonkeyPatch) -> None:
    """ar5iv 307 means 'paper not in our corpus'; the fetcher must try
    arxiv.org/html next."""
    fake = _make_fake_client(
        [
            _FakeResponse(307),  # ar5iv miss
            _FakeResponse(200, content=b"<html>fallback</html>", text="<html>fallback</html>"),
        ]
    )
    monkeypatch.setattr(_arxiv_ar5iv.httpx, "Client", lambda *a, **k: fake)
    result = _arxiv_ar5iv.fetch_html_content("2604.00001")
    assert result is not None
    assert "fallback" in result


def test_fetch_returns_none_on_total_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _make_fake_client([_FakeResponse(404), _FakeResponse(404)])
    monkeypatch.setattr(_arxiv_ar5iv.httpx, "Client", lambda *a, **k: fake)
    assert _arxiv_ar5iv.fetch_html_content("9999.99999") is None


def test_fetch_treats_empty_extracted_text_as_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200 with only stripped-tag content (no body text) is not a useful hit."""
    fake = _make_fake_client(
        [
            _FakeResponse(200, content=b"<html><script>x</script></html>", text="<html><script>x</script></html>"),
            _FakeResponse(200, content=b"<html><body>real</body></html>", text="<html><body>real</body></html>"),
        ]
    )
    monkeypatch.setattr(_arxiv_ar5iv.httpx, "Client", lambda *a, **k: fake)
    result = _arxiv_ar5iv.fetch_html_content("2401.00001")
    assert result is not None
    assert "real" in result
