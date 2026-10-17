from __future__ import annotations

import pytest
from conftest import echo, fixture_html, page_html, search_data

from autoscout24_scraper import (
    FiltersIgnoredError,
    ListingNotFoundError,
    LocationNotFoundError,
    ParseError,
    SearchQuery,
    UnknownMakeError,
    UnknownModelError,
)
from autoscout24_scraper.scraper import PRICE_CEILING, split_price

UID = "4856d9fc-5333-4c29-8ed2-0bd35c8e6422"


class ScrapeTimeoutError(Exception):
    """Same class name as the SDK's timeout error (matched by name)."""


class TargetNotFoundError(Exception):
    """Same class name as the SDK's 404 error."""


class AuthenticationError(Exception):
    pass


def test_retries_transient_errors_with_backoff(make_scraper):
    answers = [
        ScrapeTimeoutError("slow"),
        ScrapeTimeoutError("slow"),
        fixture_html("search_bmw.json"),
    ]
    scraper, client = make_scraper(lambda url, kw: answers.pop(0), backoff=1.5)
    page = scraper.search(SearchQuery(make="bmw"))
    assert len(page.listings) == 5
    assert len(client.calls) == 3
    assert scraper.sleeps == [1.5, 3.0]
    assert scraper.requests == 3


def test_retries_pages_without_data(make_scraper):
    answers = ["<html>Just a moment...</html>", fixture_html("search_bmw.json")]
    scraper, client = make_scraper(lambda url, kw: answers.pop(0))
    assert scraper.search(SearchQuery(make="bmw")).total == 61502
    assert len(client.calls) == 2


def test_gives_up_after_max_retries(make_scraper):
    scraper, client = make_scraper(lambda url, kw: ScrapeTimeoutError("slow"), max_retries=2)
    with pytest.raises(ScrapeTimeoutError):
        scraper.search()
    assert len(client.calls) == 3


def test_does_not_retry_other_errors(make_scraper):
    scraper, client = make_scraper(lambda url, kw: AuthenticationError("bad key"))
    with pytest.raises(AuthenticationError):
        scraper.search()
    assert len(client.calls) == 1


def test_proxy_country_is_passed_through(make_scraper):
    scraper, client = make_scraper(
        lambda url, kw: fixture_html("search_bmw.json"), proxy_country="DE"
    )
    scraper.search(SearchQuery(make="bmw"))
    assert client.calls[0][1] == {"proxy_country": "DE"}


def test_unknown_make_falls_back_and_is_reported(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: fixture_html("search_unknown_make.json"))
    with pytest.raises(UnknownMakeError) as info:
        scraper.search(SearchQuery(make="bmv"))
    assert info.value.suggestions == ["BMW"]
    assert "Did you mean: BMW" in str(info.value)


def test_unknown_make_with_model_is_a_404(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: TargetNotFoundError("404"))
    with pytest.raises(UnknownMakeError):
        scraper.search(SearchQuery(make="bmv", model="x1"))


def test_unknown_model_is_reported_with_suggestions(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: fixture_html("search_bmw_unknown_model.json"))
    with pytest.raises(UnknownModelError) as info:
        scraper.search(SearchQuery(make="bmw", model="3 serie"))
    assert "3-series" in info.value.suggestions


def test_unchecked_search_returns_the_fallback_page(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: fixture_html("search_bmw_unknown_model.json"))
    page = scraper.search(SearchQuery(make="bmw", model="foo"), check=False)
    assert page.total == 172942


def test_location_not_found(make_scraper):
    def responder(url, kw):  # the place is echoed back, but without coordinates
        return page_html(search_data(["a"], query={**echo(url), "cat": "ma74mo2084"}))

    scraper, _ = make_scraper(responder)
    with pytest.raises(LocationNotFoundError):
        scraper.search(SearchQuery(make="volkswagen", model="golf", zip="Nowhere", radius_km=50))


def test_redirected_slug_is_retried_on_the_sites_own_path(make_scraper):
    def responder(url, kw):
        if "/lst/bmw/3-series" in url:
            return fixture_html("search_de_redirected.json")  # filters dropped
        assert "/lst/bmw/3er?" in url and "fuel=D" in url
        return fixture_html("search_de_filtered.json")

    scraper, client = make_scraper(responder, site="de")
    query = SearchQuery(
        make="bmw", model="3-series", countries=["DE"], fuel=["diesel"], gear=["automatic"]
    )
    page = scraper.search(query)
    assert page.url.startswith("https://www.autoscout24.de/lst/bmw/3er?")
    assert page.filters["fuel"] == "D"
    assert len(client.calls) == 2
    scraper.search(query, page=2)  # the site's path is remembered
    assert "/lst/bmw/3er?" in client.calls[-1][0] and "page=2" in client.calls[-1][0]
    assert len(client.calls) == 3


def test_filters_still_missing_raise(make_scraper):
    def responder(url, kw):
        query = {**echo(url, drop=("fuel",)), "cat": "ma13"}
        return page_html(search_data(["a"], query=query, slug=["bmw"]))

    scraper, client = make_scraper(responder)
    with pytest.raises(FiltersIgnoredError) as info:
        scraper.search(SearchQuery(make="bmw", fuel=["diesel"]))
    assert info.value.dropped == {"fuel": "D"}
    assert len(client.calls) == 1


def test_search_by_url(make_scraper):
    scraper, client = make_scraper(lambda url, kw: fixture_html("search_bmw.json"))
    url = "https://www.autoscout24.com/lst/bmw?atype=C&cy=D&page=7"
    scraper.search(url, page=2)
    assert client.calls[0][0] == "https://www.autoscout24.com/lst/bmw?atype=C&cy=D&page=2"
    with pytest.raises(ValueError):
        scraper.search(f"https://www.autoscout24.com/offers/{UID}")


def paged_responder(pages: dict[int, list[str]], total: int, sponsored=frozenset()):
    def responder(url, kw):
        query = echo(url)
        data = search_data(
            pages.get(int(query["page"]), []),
            total=total,
            pages=len(pages),
            query=query,
            sponsored=set(sponsored),
        )
        return page_html(data)

    return responder


def test_iter_listings_dedupes_and_stops_on_the_last_page(make_scraper):
    pages = {1: ["s", "a", "b"], 2: ["s", "c", "b"], 3: ["d"]}
    scraper, client = make_scraper(paged_responder(pages, total=7, sponsored={"s"}))
    ids = [car.id for car in scraper.iter_listings(max_pages=None)]
    assert ids == ["s", "a", "b", "c", "d"]
    assert len(client.calls) == 3


def test_iter_listings_limits(make_scraper):
    pages = {1: ["s", "a", "b"], 2: ["s", "c", "e"], 3: ["d"]}
    scraper, client = make_scraper(paged_responder(pages, total=7, sponsored={"s"}))
    assert [c.id for c in scraper.iter_listings(organic_only=True, max_pages=None)] == [
        "a",
        "b",
        "c",
        "e",
        "d",
    ]
    scraper, client = make_scraper(paged_responder(pages, total=7))
    assert [c.id for c in scraper.collect(max_pages=None, max_results=4)] == ["s", "a", "b", "c"]
    assert len(client.calls) == 2
    scraper, client = make_scraper(paged_responder(pages, total=7))
    assert len(scraper.collect(max_pages=None, max_requests=1)) == 3
    assert len(client.calls) == 1
    scraper, client = make_scraper(paged_responder(pages, total=7))
    assert len(scraper.collect()) == 3  # one page by default


def test_split_by_price_bands(make_scraper):
    """A search over the 4,000 cap is split until every band fits."""

    def responder(url, kw):
        query = {**echo(url), "cat": "ma13"}
        low = int(query.get("pricefrom", 0))
        high = int(query["priceto"]) if "priceto" in query else None
        if high is None:
            total = 5000 if low == 0 else 300
        else:
            total = 4500 if (low, high) == (0, 100_000) else 1000
        ids = [f"{low}-{high}-{i}" for i in range(2)]
        return page_html(search_data(ids, total=total, pages=1, query=query))

    scraper, client = make_scraper(responder)
    cars = scraper.collect(SearchQuery(make="bmw"), split_by_price=True, max_pages=1)
    urls = [u for u, _ in client.calls]
    assert "pricefrom" not in urls[0] and "priceto" not in urls[0]  # whole range first
    assert "priceto=100000" in urls[1]  # 0..100,000 - still capped
    assert "priceto=3162" in urls[2]  # 0..3,162
    assert "pricefrom=3163" in urls[3] and "priceto=100000" in urls[3]
    assert "pricefrom=100001" in urls[4] and "priceto" not in urls[4]  # open top
    assert len(cars) == 6  # three final bands x two cars


def test_split_by_price_needs_a_query(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: "")
    with pytest.raises(ValueError):
        scraper.collect("https://www.autoscout24.com/lst/bmw", split_by_price=True)


def test_split_price():
    assert split_price(0, PRICE_CEILING) == 100_000
    assert split_price(0, 100_000) == 3162
    assert split_price(10, 11) == 10


def test_details_by_id_on_a_site(make_scraper):
    scraper, client = make_scraper(lambda url, kw: fixture_html("details_dealer.json"), site="de")
    car = scraper.details(UID)
    assert client.calls[0][0] == f"https://www.autoscout24.de/angebote/{UID}"
    assert car.make == "BMW"


def test_details_not_found(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: fixture_html("details_removed.json"))
    with pytest.raises(ListingNotFoundError):
        scraper.details(UID)
    scraper, _ = make_scraper(lambda url, kw: TargetNotFoundError("404"))
    with pytest.raises(ListingNotFoundError):
        scraper.details(UID)


def test_filter_options(make_scraper):
    scraper, client = make_scraper(lambda url, kw: fixture_html("search_bmw.json"))
    options = scraper.filter_options("bmw")
    assert client.calls[0][0].startswith("https://www.autoscout24.com/lst/bmw?")
    assert "3-series" in [o.slug for o in options.model_lines]
    scraper, _ = make_scraper(lambda url, kw: fixture_html("search_unknown_make.json"))
    with pytest.raises(UnknownMakeError):
        scraper.filter_options("bmv")


def test_non_html_answer_is_a_parse_error(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: {"elements": []}, max_retries=0)
    with pytest.raises(ParseError):
        scraper.search()
