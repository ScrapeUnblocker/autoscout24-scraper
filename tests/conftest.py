"""Shared test helpers: real (trimmed) AutoScout24 page data and a fake ScrapeUnblocker client.

The fixtures in ``tests/fixtures/`` are the ``__NEXT_DATA__`` JSON of real AutoScout24
pages, cut down to a few listings, with dealer names, phone numbers and street
addresses replaced. :func:`page_html` wraps them back into the script tag the pages
carry, so the parsers run on the same structure they see in production. No test
calls the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def page_html(data: dict[str, Any]) -> str:
    """A minimal AutoScout24 page carrying ``data`` as its ``__NEXT_DATA__``."""
    return (
        "<!DOCTYPE html><html><head><title>AutoScout24</title></head><body>"
        '<div id="__next"></div>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        "</body></html>"
    )


def fixture_html(name: str) -> str:
    return page_html(load_fixture(name))


def echo(url: str, drop: tuple[str, ...] = ()) -> dict[str, str]:
    """The filters of ``url`` as AutoScout24 echoes them back in ``pageQuery``."""
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items() if k not in drop}
    query.setdefault("page", "1")
    return query


def listing(uid: str, price: int | None = 10000, sponsored: bool = False) -> dict[str, Any]:
    """A minimal search-result listing."""
    return {
        "id": uid,
        "url": f"/offers/car-{uid}",
        "title": "Test Car",
        "price": {"priceFormatted": f"€ {price:,}" if price else "", "priceRaw": price},
        "vehicle": {"make": "Test", "model": "Car", "offerType": "U"},
        "seller": {"type": "Dealer", "id": "1", "companyName": "Example Autohaus"},
        "location": {"countryCode": "DE"},
        "tracking": {"firstRegistration": "01-2020", "mileage": "1000", "fuelType": "d"},
        "searchResultType": "Nfm" if sponsored else "Organic",
        "images": [],
    }


def search_data(
    ids: list[str],
    total: int | None = None,
    pages: int | None = None,
    query: dict[str, str] | None = None,
    slug: list[str] | None = None,
    prices: list[int | None] | None = None,
    sponsored: set[str] | None = None,
) -> dict[str, Any]:
    """Synthetic ``__NEXT_DATA__`` for a search page."""
    prices = prices or [10000] * len(ids)
    sponsored = sponsored or set()
    return {
        "props": {
            "pageProps": {
                "pageid": "list",
                "pageQuery": {"atype": "C", "sort": "standard", "desc": "0", **(query or {})},
                "numberOfResults": len(ids) if total is None else total,
                "numberOfPages": 1 if pages is None else pages,
                "listHeaderTitle": "Test",
                "listings": [
                    listing(uid, price, uid in sponsored) for uid, price in zip(ids, prices)
                ],
            }
        },
        "query": {"slug": slug} if slug else {},
    }


class FakeClient:
    """Stands in for ``scrapeunblocker.Client``; ``responder(url, kwargs)`` returns HTML.

    A responder may also return an exception instance, which is raised instead.
    """

    def __init__(self, responder: Callable[[str, dict[str, Any]], Any]):
        self.responder = responder
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_page_source(self, url: str, **kwargs: Any) -> str:
        self.calls.append((url, kwargs))
        result = self.responder(url, kwargs)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def make_scraper():
    """Build an :class:`AutoScout24Scraper` around a :class:`FakeClient` (no sleeping)."""
    from autoscout24_scraper import AutoScout24Scraper

    def build(responder, **kwargs):
        client = FakeClient(responder)
        sleeps: list[float] = []
        scraper = AutoScout24Scraper(client=client, sleep=sleeps.append, **kwargs)
        scraper.sleeps = sleeps  # type: ignore[attr-defined]
        return scraper, client

    return build
