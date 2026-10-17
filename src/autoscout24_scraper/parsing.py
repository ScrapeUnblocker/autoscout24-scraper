"""Turn AutoScout24 pages into :mod:`models`.

AutoScout24 is a Next.js site: every search and listing page carries its full data
as JSON in ``<script id="__NEXT_DATA__">``. The parsers read that JSON rather than
the HTML layout, so they don't break on design changes.

Search pages hold up to 20 listings plus the site's filter vocabulary
(``taxonomy``) and an echo of the filters it applied (``pageQuery``); listing pages
hold everything about one car (``listingDetails``).
"""

from __future__ import annotations

import difflib
import html as html_lib
import json
import re
from typing import Any

from .errors import ListingNotFoundError, ParseError
from .models import FilterOptions, Listing, ListingDetails, Option, SearchPage
from .urls import FUEL_NAMES, OFFER_NAMES, listing_id, slugify

_NEXT_DATA = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S | re.I)
#: Echoed parameters that are tracking noise, not filters.
_NOISE = {"query_id", "tier_rotation", "show_nfm", "pricetype", "ocs_listing", "mcat"}


# ---------------------------------------------------------------------------
# Page data
# ---------------------------------------------------------------------------


def next_data(html: str) -> dict[str, Any]:
    """The ``__NEXT_DATA__`` JSON of a page."""
    match = _NEXT_DATA.search(html or "")
    if not match:
        raise ParseError("page has no __NEXT_DATA__ block (not an AutoScout24 page?)")
    try:
        data = json.loads(match.group(1))
    except ValueError as exc:
        raise ParseError(f"__NEXT_DATA__ is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("__NEXT_DATA__ is not an object")
    return data


def page_props(html: str) -> dict[str, Any]:
    props = (next_data(html).get("props") or {}).get("pageProps")
    if not isinstance(props, dict):
        raise ParseError("__NEXT_DATA__ has no pageProps")
    return props


def router_slug(data: dict[str, Any]) -> list[str]:
    """The make/model slugs of the page that was finally served (after any redirect)."""
    slug = (data.get("query") or {}).get("slug")
    if isinstance(slug, str):
        return [slug]
    return [str(s) for s in slug] if isinstance(slug, list) else []


#: Parameters the scraper sends that AutoScout24 echoes back when it applies them.
_CHECKED = (
    "cy", "zipr", "pricefrom", "priceto", "fregfrom", "fregto", "kmfrom", "kmto",
    "powerfrom", "powerto", "powertype", "fuel", "gear", "body", "custtype", "offer",
    "bcol", "doorfrom", "seatsfrom", "sort", "desc",
)  # fmt: skip


def dropped_filters(sent: dict[str, str], applied: dict[str, str]) -> dict[str, str]:
    """Filters in ``sent`` that the page did not apply (comma lists compare as sets)."""

    def norm(value: str) -> set[str]:
        return {part.strip().upper() for part in str(value).split(",") if part.strip()}

    return {
        key: value
        for key, value in sent.items()
        if key in _CHECKED and norm(value) != norm(applied.get(key, ""))
    }


def page_kind(props: dict[str, Any]) -> str | None:
    """``"list"`` for a search page, ``"detail"`` for a listing page."""
    return props.get("pageid")


# ---------------------------------------------------------------------------
# Small value parsers
# ---------------------------------------------------------------------------


def to_int(value: Any) -> int | None:
    """An int from an int, a float or a string of digits with separators."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"\D", "", str(value))
    return int(digits) if digits else None


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_price_text(text: str | None) -> int | None:
    """``"€ 12.450,-"`` / ``"€ 3,490,-"`` / ``"€ 16 890"`` -> whole euros."""
    if not text:
        return None
    value = re.sub(r"[,.]-\s*$", "", str(text).strip())
    value = re.sub(r"[.,]\d{1,2}$", "", value)  # cents, not thousands
    return to_int(value)


def currency_of(text: str | None) -> str | None:
    if not text:
        return None
    if "€" in text:
        return "EUR"
    match = re.search(r"\b([A-Z]{3})\b", text)
    return match.group(1) if match else None


def parse_power(text: str | None) -> tuple[int | None, int | None]:
    """``"225 kW (306 hp)"`` / ``"110 kW (150 PS)"`` -> ``(225, 306)``."""
    if not text:
        return None, None
    match = re.search(r"(\d[\d.,\s]*)\s*kW\s*\(\s*(\d[\d.,\s]*)", text)
    if match:
        return to_int(match.group(1)), to_int(match.group(2))
    match = re.search(r"(\d[\d.,\s]*)\s*kW", text)
    return (to_int(match.group(1)), None) if match else (None, None)


def parse_registration(text: str | None) -> str | None:
    """``"05-2014"`` / ``"05/2014"`` / ``"2014-05-01"`` -> ``"2014-05"``."""
    if not text:
        return None
    text = str(text).strip()
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", text)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    match = re.match(r"(\d{4})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = re.fullmatch(r"(\d{4})", text)
    return match.group(1) if match else None


def year_of(registration: str | None) -> int | None:
    return int(registration[:4]) if registration and registration[:4].isdigit() else None


def price_rating(label: str | None) -> str | None:
    """AutoScout24's price evaluation (``top-price``, ``good-price``, ``fair-price``,
    ``somewhat-expensive``, ``expensive``, ...); ``None`` when not rated."""
    if not label or not isinstance(label, str):
        return None
    label = label.strip().lower()
    return None if label in ("", "unknown", "none") else label


def html_to_text(value: str | None) -> str | None:
    """The plain text of a listing description (which is HTML)."""
    if not value:
        return None
    text = re.sub(r"(?i)<br\s*/?>|</p>|</h\d>|</div>|</ul>|</ol>", "\n", value)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or None


def _absolute(url: str | None, origin: str) -> str | None:
    if not url:
        return None
    return origin + url if url.startswith("/") else url


def _seller_type(raw: str | None) -> str | None:
    if not raw:
        return None
    return {"dealer": "dealer", "privateseller": "private"}.get(raw.lower(), raw.lower())


def _offer_type(code: str | None) -> str | None:
    if not code:
        return None
    return OFFER_NAMES.get(code.upper(), code)


def _dealer_phones(seller: dict[str, Any]) -> list[str]:
    phones = []
    for phone in seller.get("phones") or []:
        if isinstance(phone, dict):
            number = phone.get("callTo") or phone.get("formattedNumber")
            if number and number not in phones:
                phones.append(number)
    return phones


# ---------------------------------------------------------------------------
# Search pages
# ---------------------------------------------------------------------------


def parse_listing(raw: dict[str, Any], origin: str) -> Listing:
    """One search result.

    Phone numbers and street addresses are only kept for dealers; private sellers'
    contact details are left out on purpose.
    """
    vehicle = raw.get("vehicle") or {}
    tracking = raw.get("tracking") or {}
    price = raw.get("price") or {}
    seller = raw.get("seller") or {}
    location = raw.get("location") or {}
    ratings = raw.get("ratings") or {}
    deal = raw.get("superDeal") or {}
    # The spec line under each card ("138,000 km", "225 kW (306 hp)", ...), keyed by its
    # icon because the labels are translated. Placeholders such as "- (g/km)" are dropped.
    facts = {
        d.get("iconName"): d.get("data")
        for d in raw.get("vehicleDetails") or []
        if isinstance(d, dict) and d.get("iconName") and re.search(r"\d", str(d.get("data") or ""))
    }
    kw, hp = parse_power(facts.get("speedometer"))
    registration = parse_registration(tracking.get("firstRegistration")) or parse_registration(
        facts.get("calendar")
    )
    mileage = to_int(tracking.get("mileage"))
    if mileage is None:
        mileage = to_int(vehicle.get("mileageInKm"))
    fuel_code = str(tracking.get("fuelType") or "").upper()
    seller_type = _seller_type(seller.get("type"))
    is_dealer = seller_type == "dealer"
    sponsored = raw.get("searchResultType") not in (None, "Organic") or any(
        isinstance(p, dict)
        and p.get("key") == "relevance_adjustment"
        and p.get("value") == "sponsored"
        for p in raw.get("trackingParameters") or []
    )
    images = [i for i in raw.get("images") or [] if isinstance(i, str)]
    uid = raw.get("id") or listing_id(raw.get("url") or "") or ""
    return Listing(
        id=uid,
        url=_absolute(raw.get("url"), origin) or f"{origin}/offers/{uid}",
        title=raw.get("title"),
        make=vehicle.get("make"),
        model=vehicle.get("model"),
        model_group=vehicle.get("modelGroup"),
        version=vehicle.get("modelVersionInput"),
        variant=vehicle.get("variant"),
        price=to_int(price.get("priceRaw")),
        currency=currency_of(price.get("priceFormatted")),
        price_rating=price_rating(tracking.get("priceLabel")),
        previous_price=(
            parse_price_text(deal.get("oldPriceFormatted")) if deal.get("isEligible") else None
        ),
        conditional_price=bool(price.get("isConditionalPrice")),
        mileage_km=mileage,
        first_registration=registration,
        year=year_of(registration),
        fuel=vehicle.get("fuel") or facts.get("gas_pump"),
        fuel_type=FUEL_NAMES.get(fuel_code) if fuel_code else None,
        transmission=vehicle.get("transmission") or facts.get("gearbox"),
        power_kw=kw,
        power_hp=hp,
        consumption=facts.get("water_drop"),
        co2_emissions=facts.get("leaf"),
        offer_type=_offer_type(vehicle.get("offerType")),
        damaged=bool(vehicle.get("isCurrentlyDamaged")),
        seller_type=seller_type,
        seller_id=str(seller["id"]) if seller.get("id") else None,
        dealer_name=seller.get("companyName") if is_dealer else None,
        dealer_rating=to_float(ratings.get("ratingsStars")) if is_dealer and ratings else None,
        dealer_reviews=to_int(ratings.get("ratingsCount")) if is_dealer and ratings else None,
        dealer_url=(seller.get("links") or {}).get("infoPage") if is_dealer else None,
        phones=_dealer_phones(seller) if is_dealer else [],
        country=location.get("countryCode"),
        zip=location.get("zip"),
        city=location.get("city"),
        street=location.get("street") if is_dealer else None,
        distance_km=to_float(location.get("distanceToSearchLocationInKm")),
        image=images[0] if images else None,
        images=images,
        sponsored=sponsored,
        new_listing=bool(raw.get("isOfferNew")),
        available_from=(raw.get("availability") or {}).get("fromDate"),
    )


def applied_filters(props: dict[str, Any]) -> dict[str, str]:
    """The filters AutoScout24 says it applied (its ``pageQuery`` echo)."""
    query = props.get("pageQuery") or {}
    return {str(k): str(v) for k, v in query.items() if k not in _NOISE and v not in (None, "")}


def recognised_make(filters: dict[str, str]) -> bool:
    return bool(re.match(r"ma\d+", filters.get("cat", ""))) or bool(
        filters.get("mmmv", "").split("|")[0]
    )


def recognised_model(filters: dict[str, str]) -> bool:
    """A model, model group (``C-Class``) or model line (``3 Series``) was applied."""
    if re.match(r"ma\d+(mo|gr|ml)\d+", filters.get("cat", "")):
        return True
    parts = filters.get("mmmv", "").split("|")
    return len(parts) > 2 and bool(parts[1] or parts[2])


def parse_search_page(html: str, url: str, origin: str) -> SearchPage:
    return search_page_from_props(page_props(html), url, origin)


def search_page_from_props(props: dict[str, Any], url: str, origin: str) -> SearchPage:
    if page_kind(props) != "list":
        raise ParseError(f"expected a search page, got {page_kind(props)!r}")
    filters = applied_filters(props)
    location = None
    if filters.get("lat") and filters.get("lon"):
        location = {
            "place": filters.get("zip"),
            "latitude": to_float(filters["lat"]),
            "longitude": to_float(filters["lon"]),
            "radius_km": to_int(filters.get("zipr")),
        }
    listings = [
        parse_listing(raw, origin) for raw in props.get("listings") or [] if isinstance(raw, dict)
    ]
    return SearchPage(
        url=url,
        page=to_int(filters.get("page")) or 1,
        total=to_int(props.get("numberOfResults")),
        pages=to_int(props.get("numberOfPages")),
        heading=props.get("listHeaderTitle"),
        listings=listings,
        filters=filters,
        location=location,
    )


# ---------------------------------------------------------------------------
# Filter vocabulary
# ---------------------------------------------------------------------------


def _options(items: Any, *, slugs: bool = False) -> list[Option]:
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value", item.get("id"))
        label = item.get("label") or item.get("name")
        if value is None or not label:
            continue
        slug = None
        if slugs:
            slug = slugify(item.get("name") or label)
        out.append(Option(value=str(value), label=str(label), slug=slug))
    return out


def page_make_id(props: dict[str, Any]) -> str | None:
    mmmv = str((props.get("pageQuery") or {}).get("mmmv") or "")
    return mmmv.split("|")[0] or None


def parse_filter_options(html: str, site: str) -> FilterOptions:
    return filter_options_from_props(page_props(html), site)


def filter_options_from_props(props: dict[str, Any], site: str) -> FilterOptions:
    tax = props.get("taxonomy") or {}
    make_id = page_make_id(props)
    by_make = (lambda key: (tax.get(key) or {}).get(make_id) or []) if make_id else (lambda key: [])
    return FilterOptions(
        site=site,
        makes=_options(tax.get("makesSorted"), slugs=True),
        models=_options(by_make("models"), slugs=True),
        model_groups=_options(by_make("modelGroups"), slugs=True),
        model_lines=_options(by_make("modelLines"), slugs=True),
        fuel=_options(tax.get("fuelType")),
        body=_options(tax.get("bodyType")),
        gear=_options(tax.get("gearing")),
        offer=_options(tax.get("offer")),
        seller=_options(tax.get("customerType")),
        color=_options(tax.get("bodyColor")),
        country=[o for o in _options(tax.get("country")) if "," not in o.value],
        sort=_options(tax.get("sortingKeys")),
    )


def suggest(name: str, candidates: list[str], n: int = 3) -> list[str]:
    """Close matches for a misspelt make or model."""
    wanted = slugify(name)
    by_slug = {slugify(c): c for c in candidates if c}
    hits = difflib.get_close_matches(wanted, list(by_slug), n=n, cutoff=0.6)
    return [by_slug[h] for h in hits]


def make_names(props: dict[str, Any]) -> list[str]:
    return [o.label for o in _options((props.get("taxonomy") or {}).get("makesSorted"))]


def model_names(props: dict[str, Any]) -> list[str]:
    tax = props.get("taxonomy") or {}
    make_id = page_make_id(props)
    if not make_id:
        return []
    names: list[str] = []
    for key in ("modelLines", "modelGroups", "models"):
        for option in _options((tax.get(key) or {}).get(make_id), slugs=True):
            if option.slug and option.slug not in names:
                names.append(option.slug)
    return names


# ---------------------------------------------------------------------------
# Listing pages
# ---------------------------------------------------------------------------


def _formatted(value: Any) -> str | None:
    return value.get("formatted") if isinstance(value, dict) else None


def _raw(value: Any) -> Any:
    return value.get("raw") if isinstance(value, dict) else None


def _equipment(value: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not isinstance(value, dict):
        return out
    for key, items in value.items():
        names = []
        category = key
        for item in items or []:
            if isinstance(item, dict) and item.get("id"):
                category = item.get("categoryName") or category
                names.append(str(item["id"]))
        if names:
            out[category] = names
    return out


def parse_details(html: str, url: str, origin: str) -> ListingDetails:
    props = page_props(html)
    details = props.get("listingDetails")
    if page_kind(props) != "detail" or not isinstance(details, dict):
        raise ListingNotFoundError(
            f"no listing at {url} (AutoScout24 redirects sold or removed cars to a search)"
        )
    v = details.get("vehicle") or {}
    prices = details.get("prices") or {}
    public = prices.get("public") or prices.get("dealer") or {}
    seller = details.get("seller") or {}
    location = details.get("location") or {}
    seller_type = _seller_type(seller.get("type"))
    is_dealer = seller_type == "dealer"
    registration = parse_registration(v.get("firstRegistrationDateRaw")) or parse_registration(
        v.get("firstRegistrationDate")
    )
    fuel = v.get("fuelCategory") or {}
    fuel_code = str(_raw(fuel) or "").upper()
    return ListingDetails(
        id=details.get("id") or listing_id(url) or "",
        url=details.get("webPage") or url,
        status=details.get("status"),
        title=details.get("title"),
        make=v.get("make"),
        model=v.get("model"),
        model_group=v.get("modelGroup"),
        version=v.get("modelVersionInput") or v.get("modelVersionCustom"),
        variant=v.get("variant"),
        body_type=v.get("bodyType"),
        price=to_int(public.get("priceRaw")),
        currency=currency_of(public.get("price")),
        net_price=to_int(public.get("netPriceRaw")),
        vat_rate=to_float(public.get("vatRate")),
        negotiable=bool(public.get("negotiable")),
        tax_deductible=bool(public.get("taxDeductible")),
        mileage_km=to_int(v.get("mileageInKmRaw")),
        first_registration=registration,
        year=year_of(registration),
        production_year=to_int(v.get("productionYear")),
        offer_type=_offer_type(v.get("offerType")),
        fuel=_formatted(fuel),
        fuel_type=FUEL_NAMES.get(fuel_code) if fuel_code else None,
        transmission=v.get("transmissionType"),
        gears=to_int(v.get("gears")),
        cylinders=to_int(v.get("cylinders")),
        displacement_cc=to_int(v.get("rawDisplacementInCCM")),
        power_kw=to_int(v.get("rawPowerInKw")),
        power_hp=to_int(v.get("rawPowerInHp")),
        drivetrain=v.get("driveTrain"),
        weight_kg=to_int(v.get("weight")),
        consumption_l_100km=to_float(_raw(v.get("fuelConsumptionCombined"))),
        co2_g_km=to_float(_raw(v.get("co2emissionInGramPerKmWithFallback"))),
        electric_range_km=to_float(_raw(v.get("electricRangeWithFallback"))),
        emission_class=_formatted(v.get("environmentEuDirective")),
        emission_sticker=_formatted(v.get("environmentBImSchV35")),
        body_color=v.get("bodyColor"),
        body_color_original=v.get("bodyColorOriginal"),
        paint_type=v.get("paintType"),
        upholstery=v.get("upholstery"),
        upholstery_color=v.get("upholsteryColor"),
        seats=to_int(v.get("numberOfSeats")),
        doors=to_int(v.get("numberOfDoors")),
        previous_owners=to_int(v.get("noOfPreviousOwners")),
        had_accident=v.get("hadAccident"),
        full_service_history=v.get("hasFullServiceHistory"),
        non_smoking=v.get("nonSmoking"),
        next_inspection=v.get("nextVehicleSafetyInspection"),
        last_service=v.get("lastTechnicalServiceDate"),
        warranty=details.get("warranty"),
        equipment=_equipment(v.get("equipment")),
        description=html_to_text(details.get("description")),
        seller_type=seller_type,
        seller_id=str(seller["id"]) if seller.get("id") else None,
        dealer_name=seller.get("companyName") if is_dealer else None,
        dealer_url=_absolute((seller.get("links") or {}).get("infoPage"), origin)
        if is_dealer
        else None,
        dealer_website=(seller.get("dealer") or {}).get("homepageUrl") if is_dealer else None,
        phones=_dealer_phones(seller) if is_dealer else [],
        country=location.get("countryCode"),
        zip=location.get("zip"),
        city=location.get("city"),
        street=location.get("street") if is_dealer else None,
        latitude=to_float(location.get("latitude")),
        longitude=to_float(location.get("longitude")),
        images=[i for i in details.get("images") or [] if isinstance(i, str)],
        created_at=details.get("createdTimestampWithOffset"),
    )
