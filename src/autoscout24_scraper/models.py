"""Typed results. Every model has ``to_dict()`` for JSON/CSV export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class _Dict:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]


@dataclass
class Listing(_Dict):
    """One car from a search results page."""

    id: str
    url: str
    title: str | None = None
    make: str | None = None
    model: str | None = None
    model_group: str | None = None
    version: str | None = None
    variant: str | None = None
    price: int | None = None
    currency: str | None = None
    price_rating: str | None = None
    previous_price: int | None = None
    conditional_price: bool = False
    mileage_km: int | None = None
    first_registration: str | None = None
    year: int | None = None
    fuel: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    power_kw: int | None = None
    power_hp: int | None = None
    consumption: str | None = None
    co2_emissions: str | None = None
    offer_type: str | None = None
    damaged: bool = False
    seller_type: str | None = None
    seller_id: str | None = None
    dealer_name: str | None = None
    dealer_rating: float | None = None
    dealer_reviews: int | None = None
    dealer_url: str | None = None
    phones: list[str] = field(default_factory=list)
    country: str | None = None
    zip: str | None = None
    city: str | None = None
    street: str | None = None
    distance_km: float | None = None
    image: str | None = None
    images: list[str] = field(default_factory=list)
    sponsored: bool = False
    new_listing: bool = False
    available_from: str | None = None


@dataclass
class SearchPage(_Dict):
    """One page of search results plus what AutoScout24 understood from the request."""

    url: str
    page: int
    total: int | None
    pages: int | None
    heading: str | None
    listings: list[Listing] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    location: dict[str, Any] | None = None

    @property
    def capped(self) -> bool:
        """True when more cars match than AutoScout24 will page through (4,000)."""
        from .urls import MAX_RESULTS

        return bool(self.total and self.total > MAX_RESULTS)


@dataclass
class ListingDetails(_Dict):
    """Everything on a listing page."""

    id: str
    url: str
    status: str | None = None
    title: str | None = None
    make: str | None = None
    model: str | None = None
    model_group: str | None = None
    version: str | None = None
    variant: str | None = None
    body_type: str | None = None
    price: int | None = None
    currency: str | None = None
    net_price: int | None = None
    vat_rate: float | None = None
    negotiable: bool = False
    tax_deductible: bool = False
    mileage_km: int | None = None
    first_registration: str | None = None
    year: int | None = None
    production_year: int | None = None
    offer_type: str | None = None
    fuel: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    gears: int | None = None
    cylinders: int | None = None
    displacement_cc: int | None = None
    power_kw: int | None = None
    power_hp: int | None = None
    drivetrain: str | None = None
    weight_kg: int | None = None
    consumption_l_100km: float | None = None
    co2_g_km: float | None = None
    electric_range_km: float | None = None
    emission_class: str | None = None
    emission_sticker: str | None = None
    body_color: str | None = None
    body_color_original: str | None = None
    paint_type: str | None = None
    upholstery: str | None = None
    upholstery_color: str | None = None
    seats: int | None = None
    doors: int | None = None
    previous_owners: int | None = None
    had_accident: bool | None = None
    full_service_history: bool | None = None
    non_smoking: bool | None = None
    next_inspection: str | None = None
    last_service: str | None = None
    warranty: Any = None
    equipment: dict[str, list[str]] = field(default_factory=dict)
    description: str | None = None
    seller_type: str | None = None
    seller_id: str | None = None
    dealer_name: str | None = None
    dealer_url: str | None = None
    dealer_website: str | None = None
    phones: list[str] = field(default_factory=list)
    country: str | None = None
    zip: str | None = None
    city: str | None = None
    street: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    images: list[str] = field(default_factory=list)
    created_at: str | None = None


@dataclass
class Option(_Dict):
    value: str
    label: str
    slug: str | None = None


@dataclass
class FilterOptions(_Dict):
    """The filter vocabulary of a site, read from a search page.

    ``models`` is filled when the page was a search for one make.
    """

    site: str
    makes: list[Option] = field(default_factory=list)
    models: list[Option] = field(default_factory=list)
    model_groups: list[Option] = field(default_factory=list)
    model_lines: list[Option] = field(default_factory=list)
    fuel: list[Option] = field(default_factory=list)
    body: list[Option] = field(default_factory=list)
    gear: list[Option] = field(default_factory=list)
    offer: list[Option] = field(default_factory=list)
    seller: list[Option] = field(default_factory=list)
    color: list[Option] = field(default_factory=list)
    country: list[Option] = field(default_factory=list)
    sort: list[Option] = field(default_factory=list)
