"""AutoScout24 sites, filter vocabularies and URL builders.

AutoScout24 runs one marketplace behind many country sites. Every site searches the
same inventory (cars for sale in eight European countries); the site decides the
language of labels such as fuel, gearbox and equipment, and which countries are
searched when you don't pick any. Domestic sites (``de``, ``at``, ``be-fr``,
``be-nl``, ``es``, ``fr``, ``it``, ``lu``, ``nl``) default to their own country;
the others default to all eight.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class Site:
    key: str
    origin: str
    language: str
    #: Path segment of listing pages (``/offers/<id>`` on autoscout24.com).
    offers: str
    prefix: str = ""

    @property
    def base(self) -> str:
        return self.origin + self.prefix


SITES: dict[str, Site] = {
    s.key: s
    for s in (
        Site("com", "https://www.autoscout24.com", "English", "offers"),
        Site("de", "https://www.autoscout24.de", "German", "angebote"),
        Site("at", "https://www.autoscout24.at", "German", "angebote"),
        Site("be-fr", "https://www.autoscout24.be", "French", "offres", "/fr"),
        Site("be-nl", "https://www.autoscout24.be", "Dutch", "aanbod", "/nl"),
        Site("es", "https://www.autoscout24.es", "Spanish", "anuncios"),
        Site("fr", "https://www.autoscout24.fr", "French", "offres"),
        Site("it", "https://www.autoscout24.it", "Italian", "annunci"),
        Site("lu", "https://www.autoscout24.lu", "French", "offres"),
        Site("nl", "https://www.autoscout24.nl", "Dutch", "aanbod"),
        Site("pl", "https://www.autoscout24.pl", "Polish", "oferta"),
        Site("ro", "https://www.autoscout24.ro", "Romanian", "oferte"),
        Site("bg", "https://www.autoscout24.bg", "Bulgarian", "objava"),
        Site("cz", "https://www.autoscout24.cz", "Czech", "nabidky"),
        Site("hu", "https://www.autoscout24.hu", "Hungarian", "ajanlat"),
        Site("hr", "https://www.autoscout24.hr", "Croatian", "ponude"),
        Site("se", "https://www.autoscout24.se", "Swedish", "erbjudanden"),
        Site("tr", "https://www.autoscout24.com.tr", "Turkish", "teklifler"),
        Site("ua", "https://www.autoscout24.com.ua", "Ukrainian", "proposyzii"),
    )
}

#: ISO country code -> AutoScout24 country code (the ``cy`` parameter).
COUNTRIES: dict[str, str] = {
    "AT": "A",
    "BE": "B",
    "DE": "D",
    "ES": "E",
    "FR": "F",
    "IT": "I",
    "LU": "L",
    "NL": "NL",
}

#: Friendly name -> AutoScout24 fuel code.
FUELS: dict[str, str] = {
    "gasoline": "B",
    "petrol": "B",
    "diesel": "D",
    "electric": "E",
    "hybrid": "2",
    "hybrid-gasoline": "2",
    "hybrid-diesel": "3",
    "lpg": "L",
    "cng": "C",
    "hydrogen": "H",
    "ethanol": "M",
    "other": "O",
}

#: AutoScout24 fuel code -> canonical English name (the same on every site).
FUEL_NAMES: dict[str, str] = {
    "B": "gasoline",
    "D": "diesel",
    "E": "electric",
    "2": "hybrid-gasoline",
    "3": "hybrid-diesel",
    "L": "lpg",
    "C": "cng",
    "H": "hydrogen",
    "M": "ethanol",
    "O": "other",
}

GEARS: dict[str, str] = {"automatic": "A", "manual": "M", "semi-automatic": "S"}

BODIES: dict[str, int] = {
    "compact": 1,
    "convertible": 2,
    "coupe": 3,
    "suv": 4,
    "station-wagon": 5,
    "wagon": 5,
    "sedan": 6,
    "van": 12,
    "transporter": 13,
    "other": 7,
}

SELLERS: dict[str, str] = {"dealer": "D", "private": "P"}

#: Offer type -> code. "used" and "new" are the usual ones; the rest are special kinds.
OFFERS: dict[str, str] = {
    "new": "N",
    "used": "U",
    "employee": "J",
    "classic": "O",
    "demo": "D",
    "pre-registered": "S",
}
OFFER_NAMES: dict[str, str] = {code: name for name, code in OFFERS.items()}

COLORS: dict[str, int] = {
    "beige": 1,
    "blue": 2,
    "brown": 3,
    "bronze": 4,
    "yellow": 5,
    "grey": 6,
    "green": 7,
    "red": 10,
    "black": 11,
    "silver": 12,
    "violet": 13,
    "white": 14,
    "orange": 15,
    "gold": 16,
}

#: Sort name -> (AutoScout24 sort key, descending by default).
SORTS: dict[str, tuple[str, bool]] = {
    "best": ("standard", False),
    "newest": ("age", True),
    "price": ("price", False),
    "mileage": ("mileage", False),
    "year": ("year", False),
    "power": ("power", False),
    "distance": ("distance", False),
    "make": ("make", False),
}

#: AutoScout24 serves at most 200 pages of 20 listings for one search.
PAGE_SIZE = 20
MAX_PAGES = 200
MAX_RESULTS = PAGE_SIZE * MAX_PAGES

_UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)


def get_site(key: str | Site) -> Site:
    if isinstance(key, Site):
        return key
    try:
        return SITES[key.lower().strip()]
    except KeyError:
        raise ValueError(f"unknown site {key!r}; choose one of: {', '.join(SITES)}") from None


def slugify(name: str) -> str:
    """AutoScout24's URL slug for a make or model name.

    ``"Mercedes-Benz"`` -> ``mercedes-benz``, ``"C 200"`` -> ``c-200``,
    ``"3 Series"`` -> ``3-series``, ``"ID.3"`` -> ``id.3``, ``"Citroën"`` -> ``citroen``.
    """
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"\s+", "-", text.strip().lower())
    text = re.sub(r"[^a-z0-9.+\-]", "", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def _codes(values: Iterable[str | int] | None, table: dict[str, Any], what: str) -> str | None:
    """Map friendly names (or raw codes) to a comma-joined AutoScout24 parameter."""
    if not values:
        return None
    raw_codes = {str(v).upper() for v in table.values()}
    out: list[str] = []
    for value in values:
        key = str(value).strip()
        if not key:
            continue
        if key.lower() in table:
            code = str(table[key.lower()])
        elif key.upper() in raw_codes:
            code = key.upper()
        else:
            names = ", ".join(sorted(table))
            raise ValueError(f"unknown {what} {value!r}; choose from: {names}")
        if code not in out:
            out.append(code)
    return ",".join(out) or None


def country_codes(countries: Iterable[str] | None) -> str | None:
    """``["DE", "AT"]`` -> ``"D,A"``."""
    if not countries:
        return None
    out = []
    for country in countries:
        iso = country.strip().upper()
        if iso in COUNTRIES:
            code = COUNTRIES[iso]
        elif iso in COUNTRIES.values():
            code = iso
        else:
            raise ValueError(
                f"unknown country {country!r}; AutoScout24 lists cars in: {', '.join(COUNTRIES)}"
            )
        if code not in out:
            out.append(code)
    return ",".join(out)


@dataclass
class SearchQuery:
    """A car search. Every field is optional; unset fields are not sent.

    ``make`` and ``model`` are names or URL slugs (``"BMW"``, ``"3 Series"``, ``"x1"``).
    Lists accept the friendly names in this module (``fuel=["diesel", "hybrid"]``) or
    AutoScout24's own codes. ``extra`` is passed straight through as URL parameters,
    for any filter not covered here.
    """

    make: str | None = None
    model: str | None = None
    countries: list[str] = field(default_factory=list)
    zip: str | None = None
    radius_km: int | None = None
    price_min: int | None = None
    price_max: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    km_min: int | None = None
    km_max: int | None = None
    power_min: int | None = None
    power_max: int | None = None
    power_unit: str = "kw"
    fuel: list[str] = field(default_factory=list)
    gear: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    seller: str | None = None
    offer: list[str] = field(default_factory=list)
    color: list[str] = field(default_factory=list)
    doors_min: int | None = None
    seats_min: int | None = None
    sort: str = "best"
    descending: bool | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def with_prices(self, low: int | None, high: int | None) -> SearchQuery:
        return replace(self, price_min=low, price_max=high)

    def path(self) -> str:
        if not self.make:
            if self.model:
                raise ValueError("a model needs a make")
            return "/lst"
        path = "/lst/" + slugify(self.make)
        if self.model:
            path += "/" + slugify(self.model)
        return path

    def params(self, page: int = 1) -> dict[str, str]:
        if self.sort not in SORTS:
            raise ValueError(f"unknown sort {self.sort!r}; choose from: {', '.join(SORTS)}")
        if self.power_unit not in ("kw", "hp"):
            raise ValueError("power_unit must be 'kw' or 'hp'")
        if self.radius_km is not None and not self.zip:
            raise ValueError("radius_km needs a zip (postal code or place)")
        sort_key, default_desc = SORTS[self.sort]
        desc = default_desc if self.descending is None else self.descending
        seller = _codes([self.seller] if self.seller else None, SELLERS, "seller type")
        values: dict[str, Any] = {
            "atype": "C",
            "cy": country_codes(self.countries),
            "zip": self.zip,
            "zipr": self.radius_km,
            "pricefrom": self.price_min,
            "priceto": self.price_max,
            "fregfrom": self.year_min,
            "fregto": self.year_max,
            "kmfrom": self.km_min,
            "kmto": self.km_max,
            "powerfrom": self.power_min,
            "powerto": self.power_max,
            "powertype": self.power_unit,
            "fuel": _codes(self.fuel, FUELS, "fuel"),
            "gear": _codes(self.gear, GEARS, "gearbox"),
            "body": _codes(self.body, BODIES, "body type"),
            "custtype": seller,
            "offer": _codes(self.offer, OFFERS, "offer type"),
            "bcol": _codes(self.color, COLORS, "colour"),
            "doorfrom": self.doors_min,
            "seatsfrom": self.seats_min,
            "sort": sort_key,
            "desc": "1" if desc else "0",
        }
        params = {
            k: str(v)
            for k, v in values.items()
            if v not in (None, "") and not (k.endswith("from") and v == 0)  # 0 = no minimum
        }
        params.update({str(k): str(v) for k, v in self.extra.items()})
        if page > 1:
            params["page"] = str(page)
        return params


def search_url(
    query: SearchQuery, page: int = 1, site: str | Site = "com", path: str | None = None
) -> str:
    """The AutoScout24 search URL for ``query`` and ``page`` on ``site``.

    ``path`` overrides the ``/lst/<make>/<model>`` path (e.g. with a site's own slug).
    """
    path = path or query.path()
    return get_site(site).base + path + "?" + urlencode(query.params(page), safe=",")


def with_page(url: str, page: int) -> str:
    """``url`` (a search URL copied from a browser) pointing at ``page``."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
    if page > 1:
        query.append(("page", str(page)))
    return urlunsplit(parts._replace(query=urlencode(query, safe=",|")))


def listing_id(value: str) -> str | None:
    """The listing UUID in a listing URL (or the UUID itself), else ``None``."""
    found = _UUID.findall(value or "")
    return found[-1].lower() if found else None


def listing_url(id_or_url: str, site: str | Site = "com") -> str:
    """An absolute listing URL. Bare IDs resolve on ``site``
    (``https://www.autoscout24.com/offers/<id>``, ``.../angebote/<id>`` on .de, ...)."""
    value = id_or_url.strip()
    if value.startswith(("http://", "https://")):
        return value
    target = get_site(site)
    if value.startswith("/"):
        return target.origin + value
    uid = listing_id(value)
    if not uid:
        raise ValueError(f"not an AutoScout24 listing ID or URL: {id_or_url!r}")
    return f"{target.base}/{target.offers}/{uid}"


def is_search_url(url: str) -> bool:
    path = urlsplit(url).path
    return bool(re.search(r"(^|/)lst(/|$)", path))
