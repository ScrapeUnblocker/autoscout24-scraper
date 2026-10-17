"""Scrape AutoScout24 car listings through the ScrapeUnblocker API.

>>> from autoscout24_scraper import AutoScout24Scraper, SearchQuery
>>> scraper = AutoScout24Scraper()  # reads SCRAPEUNBLOCKER_KEY
>>> cars = scraper.collect(SearchQuery(make="bmw", model="x1", countries=["DE"]), max_pages=2)
>>> car = scraper.details(cars[0].id)

See https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import (
    AutoScout24Error,
    FiltersIgnoredError,
    ListingNotFoundError,
    LocationNotFoundError,
    ParseError,
    UnknownMakeError,
    UnknownModelError,
)
from .models import FilterOptions, Listing, ListingDetails, Option, SearchPage
from .scraper import AutoScout24Scraper
from .urls import MAX_RESULTS, SITES, SearchQuery, search_url

__all__ = [
    "AutoScout24Error",
    "AutoScout24Scraper",
    "FilterOptions",
    "FiltersIgnoredError",
    "Listing",
    "ListingDetails",
    "ListingNotFoundError",
    "LocationNotFoundError",
    "MAX_RESULTS",
    "Option",
    "ParseError",
    "SITES",
    "SearchPage",
    "SearchQuery",
    "UnknownMakeError",
    "UnknownModelError",
    "__version__",
    "search_url",
]
