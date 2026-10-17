from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from autoscout24_scraper.urls import (
    SITES,
    SearchQuery,
    country_codes,
    get_site,
    is_search_url,
    listing_id,
    listing_url,
    search_url,
    slugify,
    with_page,
)

UID = "4856d9fc-5333-4c29-8ed2-0bd35c8e6422"


@pytest.mark.parametrize(
    "name, slug",
    [
        ("BMW", "bmw"),
        ("Mercedes-Benz", "mercedes-benz"),
        ("C 200", "c-200"),
        ("3 Series", "3-series"),
        ("Range Rover Evoque", "range-rover-evoque"),
        ("ID.3", "id.3"),
        ("Citroën", "citroen"),
        ("  Alfa   Romeo ", "alfa-romeo"),
        ("x1", "x1"),
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug


def params(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_search_url_maps_friendly_names_to_codes():
    query = SearchQuery(
        make="BMW",
        model="X1",
        countries=["de", "AT"],
        price_max=30000,
        year_min=2019,
        km_max=80000,
        fuel=["diesel", "hybrid"],
        gear=["automatic"],
        body=["suv", "station-wagon"],
        seller="dealer",
        offer=["used", "demo"],
        color=["black"],
    )
    url = search_url(query)
    assert url.startswith("https://www.autoscout24.com/lst/bmw/x1?")
    assert params(url) == {
        "atype": "C",
        "cy": "D,A",
        "priceto": "30000",
        "fregfrom": "2019",
        "kmto": "80000",
        "powertype": "kw",
        "fuel": "D,2",
        "gear": "A",
        "body": "4,5",
        "custtype": "D",
        "offer": "U,D",
        "bcol": "11",
        "sort": "standard",
        "desc": "0",
    }
    assert "%2C" not in url  # commas stay readable


def test_raw_codes_are_accepted_and_deduplicated():
    query = SearchQuery(fuel=["D", "diesel", "B"], countries=["D", "NL"])
    p = params(search_url(query))
    assert p["fuel"] == "D,B"
    assert p["cy"] == "D,NL"


def test_sort_defaults_and_overrides():
    assert params(search_url(SearchQuery(sort="newest")))["desc"] == "1"
    assert params(search_url(SearchQuery(sort="newest")))["sort"] == "age"
    assert params(search_url(SearchQuery(sort="price")))["desc"] == "0"
    assert params(search_url(SearchQuery(sort="price", descending=True)))["desc"] == "1"


def test_page_power_unit_zero_minimum_and_extra():
    query = SearchQuery(power_min=100, power_unit="hp", price_min=0, extra={"eq": "37"})
    p = params(search_url(query, page=3))
    assert p["page"] == "3"
    assert p["powerfrom"] == "100"
    assert p["powertype"] == "hp"
    assert "pricefrom" not in p  # 0 means no minimum
    assert p["eq"] == "37"
    assert "page" not in params(search_url(query, page=1))


def test_zip_and_radius():
    p = params(search_url(SearchQuery(zip="80331", radius_km=50, sort="distance")))
    assert (p["zip"], p["zipr"], p["sort"]) == ("80331", "50", "distance")
    with pytest.raises(ValueError, match="radius_km needs a zip"):
        search_url(SearchQuery(radius_km=50))


@pytest.mark.parametrize(
    "query, message",
    [
        (SearchQuery(fuel=["steam"]), "unknown fuel"),
        (SearchQuery(body=["tank"]), "unknown body type"),
        (SearchQuery(countries=["US"]), "unknown country"),
        (SearchQuery(sort="cheapest"), "unknown sort"),
        (SearchQuery(model="x1"), "a model needs a make"),
        (SearchQuery(power_unit="ps"), "power_unit"),
    ],
)
def test_invalid_queries_raise(query, message):
    with pytest.raises(ValueError, match=message):
        search_url(query)


def test_sites():
    assert search_url(SearchQuery(make="audi"), site="de").startswith(
        "https://www.autoscout24.de/lst/audi?"
    )
    assert search_url(SearchQuery(make="bmw"), site="be-nl").startswith(
        "https://www.autoscout24.be/nl/lst/bmw?"
    )
    assert get_site("TR").origin == "https://www.autoscout24.com.tr"
    assert all(site.offers for site in SITES.values())
    with pytest.raises(ValueError, match="unknown site"):
        get_site("us")


def test_country_codes():
    assert country_codes(["de", "be", "lu"]) == "D,B,L"
    assert country_codes(None) is None


def test_with_page_replaces_the_page_parameter():
    url = "https://www.autoscout24.com/lst/audi/a4?atype=C&cy=D%2CA&page=4&fuel=D"
    assert params(with_page(url, 2)) == {"atype": "C", "cy": "D,A", "fuel": "D", "page": "2"}
    assert "page" not in params(with_page(url, 1))


def test_listing_ids_and_urls():
    url = f"https://www.autoscout24.com/offers/bmw-435-gasoline-red-cat_ma13mo20288-{UID}"
    assert listing_id(url) == UID
    assert listing_id(UID.upper()) == UID
    assert listing_id("not-a-listing") is None
    assert listing_url(UID) == f"https://www.autoscout24.com/offers/{UID}"
    assert listing_url(UID, "de") == f"https://www.autoscout24.de/angebote/{UID}"
    assert listing_url(UID, "be-fr") == f"https://www.autoscout24.be/fr/offres/{UID}"
    assert listing_url(url) == url
    assert listing_url(f"/angebote/x-{UID}", "de") == f"https://www.autoscout24.de/angebote/x-{UID}"
    with pytest.raises(ValueError):
        listing_url("hello")


def test_is_search_url():
    assert is_search_url("https://www.autoscout24.com/lst/bmw?atype=C")
    assert is_search_url("https://www.autoscout24.be/fr/lst?atype=C")
    assert not is_search_url(f"https://www.autoscout24.com/offers/{UID}")
