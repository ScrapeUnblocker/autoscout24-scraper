from __future__ import annotations

import pytest
from conftest import fixture_html, page_html

from autoscout24_scraper.errors import ListingNotFoundError, ParseError
from autoscout24_scraper.parsing import (
    applied_filters,
    dropped_filters,
    html_to_text,
    make_names,
    model_names,
    next_data,
    page_props,
    parse_details,
    parse_filter_options,
    parse_power,
    parse_price_text,
    parse_registration,
    parse_search_page,
    price_rating,
    recognised_make,
    recognised_model,
    router_slug,
    suggest,
)

COM = "https://www.autoscout24.com"
IT = "https://www.autoscout24.it"


@pytest.fixture(scope="module")
def bmw():
    return parse_search_page(fixture_html("search_bmw.json"), "u", COM)


@pytest.fixture(scope="module")
def fiat():
    return parse_search_page(fixture_html("search_fiat_milano.json"), "u", IT)


def test_search_page_meta(bmw):
    assert bmw.total == 61502
    assert bmw.pages == 200
    assert bmw.page == 1
    assert bmw.heading == "61,502 listings for BMW"
    assert bmw.capped is True
    assert bmw.filters["cat"] == "ma13"
    assert "query_id" not in bmw.filters  # tracking noise is dropped
    assert bmw.location is None


def test_dealer_listing(bmw):
    car = bmw.listings[0]
    assert car.id == "4856d9fc-5333-4c29-8ed2-0bd35c8e6422"
    assert car.url.startswith(f"{COM}/offers/bmw-435-")
    assert (car.make, car.model, car.model_group, car.variant) == (
        "BMW",
        "435",
        "4 Series",
        "Coupe",
    )
    assert car.version == "435 i xDrive/Pdc/Leder/Navi/Shz/Tempo"
    assert (car.price, car.currency, car.price_rating) == (20999, "EUR", "good-price")
    assert (car.mileage_km, car.first_registration, car.year) == (138000, "2014-05", 2014)
    assert (car.fuel, car.fuel_type, car.transmission) == ("Gasoline", "gasoline", "Automatic")
    assert (car.power_kw, car.power_hp) == (225, 306)
    assert car.offer_type == "used"
    assert car.seller_type == "dealer"
    assert car.dealer_name == "Example Autohaus 162"
    assert car.phones == ["+493000000001", "+493000000002"]
    assert (car.country, car.zip, car.city, car.street) == (
        "DE",
        "64521",
        "Groß-Gerau",
        "Example Street 1",
    )
    assert car.image == car.images[0]
    assert car.new_listing is True
    assert car.sponsored is False


def test_dealer_rating_previous_price_and_placeholders(bmw):
    rated = bmw.listings[1]
    assert (rated.dealer_rating, rated.dealer_reviews) == (5.0, 69)
    deal = bmw.listings[3]
    assert (deal.price, deal.previous_price) == (2999, 3490)
    assert bmw.listings[0].co2_emissions is None  # "- (g/km)" placeholder dropped
    wltp = bmw.listings[4]
    assert wltp.consumption == "6,8 l/100 km (komb.)"
    assert wltp.co2_emissions == "153 g/km (komb.)"
    assert wltp.fuel_type == "gasoline"  # code-based, even though the label is German
    assert wltp.fuel == "Benzin"


def test_sponsored_private_and_location(fiat):
    assert fiat.location == {
        "place": "Milano",
        "latitude": 45.46362,
        "longitude": 9.18812,
        "radius_km": 50,
    }
    sponsored = [c.sponsored for c in fiat.listings]
    assert sponsored == [True, True, False, False]
    assert fiat.listings[0].conditional_price is True
    assert fiat.listings[0].distance_km == 22.0
    assert fiat.listings[1].price_rating == "toolow-price"  # trailing space stripped
    private = fiat.listings[2]
    assert private.seller_type == "private"
    assert private.phones == []  # private sellers' contact details are not kept
    assert private.street is None
    assert private.dealer_name is None and private.dealer_url is None
    assert private.city == "Vigevano"
    assert private.url.startswith(f"{IT}/annunci/")


def test_filter_options():
    options = parse_filter_options(fixture_html("search_bmw.json"), "com")
    assert options.site == "com"
    assert ("13", "BMW", "bmw") in [(o.value, o.label, o.slug) for o in options.makes]
    assert ("38", "3 Series (all)", "3-series") in [
        (o.value, o.label, o.slug) for o in options.model_lines
    ]
    assert ("1640", "318") in [(o.value, o.label) for o in options.models]
    assert {o.value for o in options.fuel} >= {"B", "D", "E", "2"}
    assert [o.value for o in options.country] == ["A", "B", "D", "E", "F", "I", "L", "NL"]
    assert "age" in [o.value for o in options.sort]


def test_unknown_make_and_model_fallback_pages():
    model_page = page_props(fixture_html("search_bmw_unknown_model.json"))
    filters = applied_filters(model_page)
    assert recognised_make(filters) and not recognised_model(filters)
    assert "3-series" in model_names(model_page)
    make_page = page_props(fixture_html("search_unknown_make.json"))
    assert not recognised_make(applied_filters(make_page))
    assert suggest("bmv", make_names(make_page)) == ["BMW"]
    assert suggest("mercedes", make_names(make_page)) == ["Mercedes-Benz"]


@pytest.mark.parametrize(
    "filters, model",
    [
        ({"cat": "ma13mo20288"}, True),  # model
        ({"cat": "ma47gr100056", "mmmv": "47|||"}, True),  # model group (C-Class)
        ({"cat": "ma13ml38", "mmmv": "13||38|"}, True),  # model line (3 Series)
        ({"cat": "ma13", "mmmv": "13|||"}, False),
        ({}, False),
    ],
)
def test_recognised_model(filters, model):
    assert recognised_model(filters) is model


def test_redirect_detection():
    data = next_data(fixture_html("search_de_redirected.json"))
    assert router_slug(data) == ["bmw", "3er"]
    served = applied_filters(page_props(fixture_html("search_de_redirected.json")))
    sent = {"cy": "D", "fuel": "D", "gear": "A", "sort": "standard", "desc": "0", "page": "2"}
    assert dropped_filters(sent, served) == {"fuel": "D", "gear": "A"}
    filtered = applied_filters(page_props(fixture_html("search_de_filtered.json")))
    assert dropped_filters(sent, filtered) == {}
    assert dropped_filters({"fuel": "B,D"}, {"fuel": "D,B"}) == {}


def test_details_dealer():
    car = parse_details(fixture_html("details_dealer.json"), "u", COM)
    assert car.id == "4856d9fc-5333-4c29-8ed2-0bd35c8e6422"
    assert car.status == "Active"
    assert car.url.startswith(f"{COM}/offers/")
    assert (car.price, car.currency) == (20999, "EUR")
    assert (car.body_type, car.doors, car.seats) == ("Coupe", 2, 4)
    assert (car.gears, car.cylinders, car.drivetrain) == (8, 6, "4x4")
    assert (car.power_kw, car.power_hp) == (225, 306)
    assert (car.consumption_l_100km, car.co2_g_km) == (7.6, 178.0)
    assert (car.emission_class, car.emission_sticker) == ("Euro 6", "4 (Green)")
    assert (car.body_color, car.body_color_original) == ("Red", "MELBOURNEROT METALLIC")
    assert car.next_inspection == "06/2027"
    assert car.first_registration == "2014-05"
    assert "Comfort & Convenience" in car.equipment
    assert car.equipment["Safety & Security"][0] == "ABS"
    assert car.description and car.description.startswith("BMW 435i xDrive")
    assert "<" not in car.description
    assert "\n- Erstzulassung: 05/2014" in car.description
    assert car.phones and car.street == "Example Street 1"
    assert (car.latitude, car.longitude) == (49.91136, 8.48803)
    assert car.created_at == "2026-10-15T14:07:22.085Z"


def test_details_private_seller():
    car = parse_details(fixture_html("details_private.json"), "u", COM)
    assert car.seller_type == "private"
    assert car.phones == [] and car.street is None and car.dealer_name is None
    assert (car.net_price, car.vat_rate) == (12213, 22.0)
    assert (car.displacement_cc, car.weight_kg) == (999, 980)
    assert car.fuel_type == "hybrid-gasoline"


def test_removed_listing_raises_not_found():
    with pytest.raises(ListingNotFoundError):
        parse_details(fixture_html("details_removed.json"), "u", COM)


def test_pages_without_data():
    with pytest.raises(ParseError):
        page_props("<html><body>Access denied</body></html>")
    with pytest.raises(ParseError):
        parse_search_page(fixture_html("details_dealer.json"), "u", COM)
    with pytest.raises(ParseError):
        next_data('<script id="__NEXT_DATA__" type="application/json">{oops</script>')


@pytest.mark.parametrize(
    "text, value",
    [
        ("€ 12.450,-", 12450),
        ("€ 3,490,-", 3490),
        ("€ 16 890,-", 16890),
        ("€ 64,700,-", 64700),
        ("€ 9.940,50", 9940),
        ("", None),
        (None, None),
    ],
)
def test_parse_price_text(text, value):
    assert parse_price_text(text) == value


@pytest.mark.parametrize(
    "text, value",
    [
        ("225 kW (306 hp)", (225, 306)),
        ("110 kW (150 PS)", (110, 150)),
        ("81 kW (110 CH)", (81, 110)),
        ("1.000 kW (1.360 PS)", (1000, 1360)),
        ("70 kW", (70, None)),
        ("- kW (- hp)", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_power(text, value):
    assert parse_power(text) == value


@pytest.mark.parametrize(
    "text, value",
    [
        ("05-2014", "2014-05"),
        ("5/2014", "2014-05"),
        ("2014-05-01", "2014-05"),
        ("2014", "2014"),
        ("new", None),
        (None, None),
    ],
)
def test_parse_registration(text, value):
    assert parse_registration(text) == value


def test_price_rating_and_html_to_text():
    assert price_rating("toolow-price ") == "toolow-price"
    assert price_rating("unknown") is None
    assert price_rating(None) is None
    text = html_to_text(
        "Nice car.<br />Full history<ul><li><strong>TÜV:</strong> new</li></ul>&amp; more"
    )
    assert text == "Nice car.\nFull history\n- TÜV: new\n& more"
    assert html_to_text("") is None


def test_minimal_page_html_roundtrip():
    html = page_html({"props": {"pageProps": {"pageid": "list", "listings": []}}})
    page = parse_search_page(html, "u", COM)
    assert page.listings == [] and page.total is None
