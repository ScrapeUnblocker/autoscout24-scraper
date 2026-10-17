"""Scrape AutoScout24 through the ScrapeUnblocker ``getPageSource`` API.

:class:`AutoScout24Scraper` builds AutoScout24 URLs, fetches the pages through
ScrapeUnblocker and parses the JSON every page embeds.

* A search shows 20 cars per page and at most 200 pages (4,000 cars). Ask for more
  with ``split_by_price=True``: the price range is split into bands that each fit
  under the cap, and the bands are collected one after another (deduplicated).
* AutoScout24 ignores a make, model or location it does not recognise and quietly
  shows a broader search instead. The scraper checks the filters the page says it
  applied and raises :class:`UnknownMakeError`, :class:`UnknownModelError` or
  :class:`LocationNotFoundError` rather than return the wrong cars.
* Timeouts, transient API errors and pages that come back without their data are
  retried with doubling backoff.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from typing import Any, Callable, Union
from urllib.parse import urlsplit

from .errors import (
    AutoScout24Error,
    FiltersIgnoredError,
    ListingNotFoundError,
    LocationNotFoundError,
    ParseError,
    UnknownMakeError,
    UnknownModelError,
)
from .models import FilterOptions, Listing, ListingDetails, SearchPage
from .parsing import (
    applied_filters,
    dropped_filters,
    filter_options_from_props,
    make_names,
    model_names,
    next_data,
    page_props,
    parse_details,
    recognised_make,
    recognised_model,
    router_slug,
    search_page_from_props,
    suggest,
)
from .urls import (
    MAX_PAGES,
    SearchQuery,
    Site,
    get_site,
    is_search_url,
    listing_url,
    search_url,
    with_page,
)

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError", "NotFoundError")

#: Upper price bound used when splitting a search without a maximum price.
PRICE_CEILING = 100_000_000

Query = Union[SearchQuery, str]


def _is_named(error: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


def split_price(low: int, high: int) -> int:
    """Where to cut the price band ``low..high`` in two.

    Car prices are spread roughly logarithmically, so the cut is the geometric mean
    (with a floor of 100), e.g. ``0..100,000,000`` splits at 100,000.
    """
    mid = int(math.sqrt(max(low, 100) * max(high, 1)))
    return max(low, min(mid, high - 1))


class AutoScout24Scraper:
    """Search AutoScout24 car listings and read listing pages.

    Args:
        api_key: Your ScrapeUnblocker API key. Defaults to the
            ``SCRAPEUNBLOCKER_KEY`` environment variable (read by the SDK).
        client: A ready ``scrapeunblocker.Client`` (or anything with a compatible
            ``get_page_source``); handy for tests.
        site: Which AutoScout24 site to use (see :data:`urls.SITES`). It sets the
            language of labels and, when you pick no country, which countries
            are searched.
        proxy_country: Optional country to route requests through.
        max_retries: Extra attempts for a request that fails transiently.
        backoff: Seconds before the first retry; doubles on each retry.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any = None,
        site: str | Site = "com",
        proxy_country: str | None = None,
        max_retries: int = 3,
        backoff: float = 2.0,
        timeout: float = 180.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if client is None:
            from scrapeunblocker import Client

            client = Client(api_key=api_key, timeout=timeout)
        self.client = client
        self.site = get_site(site)
        self.proxy_country = proxy_country
        self.max_retries = max_retries
        self.backoff = backoff
        self.sleep = sleep
        #: Number of API requests made so far (each page fetch is one request).
        self.requests = 0
        # (site, our /lst/<make>/<model> path) -> the path the site really uses.
        self._paths: dict[tuple[str, str], str] = {}

    # -- fetching ---------------------------------------------------------

    def fetch(self, url: str, *, not_found: type[AutoScout24Error] = AutoScout24Error) -> str:
        """The HTML of ``url``, retried on transient failures."""
        kwargs: dict[str, Any] = {}
        if self.proxy_country:
            kwargs["proxy_country"] = self.proxy_country
        attempt = 0
        while True:
            self.requests += 1
            try:
                html = self.client.get_page_source(url, **kwargs)
                if not isinstance(html, str):
                    raise ParseError(f"expected HTML from {url}, got {type(html).__name__}")
                next_data(html)
                return html
            except Exception as exc:
                if _is_named(exc, *_NOT_FOUND_NAMES):
                    raise not_found(f"AutoScout24 answered 404 for {url}") from exc
                retryable = isinstance(exc, ParseError) or _is_named(exc, *_TRANSIENT_NAMES)
                if not retryable or attempt >= self.max_retries:
                    raise
                self.sleep(self.backoff * (2**attempt))
                attempt += 1

    # -- search -------------------------------------------------------------

    def url_for(self, query: Query, page: int = 1) -> str:
        if isinstance(query, str):
            if not is_search_url(query):
                raise ValueError(f"not an AutoScout24 search URL: {query!r}")
            return with_page(query, page)
        path = self._paths.get((self.site.key, query.path()))
        return search_url(query, page, self.site, path)

    def search(
        self, query: Query | None = None, page: int = 1, *, check: bool = True
    ) -> SearchPage:
        """One page of results for ``query`` (a :class:`SearchQuery` or a search URL).

        With ``check`` (the default) the page is compared with what was asked for:

        * :class:`UnknownMakeError` / :class:`UnknownModelError` /
          :class:`LocationNotFoundError` when AutoScout24 did not recognise them;
        * a model slug that is not the site's own (``3-series`` on autoscout24.de,
          where it is ``3er``) is redirected by AutoScout24 *without your filters*.
          The scraper then repeats the request once on the site's slug (and
          remembers it); :class:`FiltersIgnoredError` if filters are still missing.
        """
        query = SearchQuery() if query is None else query
        url = self.url_for(query, page)
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        try:
            data = next_data(self.fetch(url))
        except AutoScout24Error as exc:
            # /lst/<make>/<model> with an unknown make is a 404 (an unknown make
            # alone falls back to all cars, which the checks below catch).
            if check and isinstance(query, SearchQuery) and query.make and "404" in str(exc):
                raise UnknownMakeError(query.make) from exc
            raise
        props = (data.get("props") or {}).get("pageProps") or {}
        result = search_page_from_props(props, url, origin)
        if not check or not isinstance(query, SearchQuery):
            return result
        if query.make and not recognised_make(result.filters):
            raise UnknownMakeError(query.make, suggest(query.make, make_names(props)))
        if query.model and not recognised_model(result.filters):
            raise UnknownModelError(
                query.make or "", query.model, suggest(query.model, model_names(props))
            )
        dropped = dropped_filters(query.params(page), result.filters)
        if dropped:
            slug = router_slug(data)
            served = "/lst/" + "/".join(slug) if slug else "/lst"
            current = self._paths.get((self.site.key, query.path()), query.path())
            if served != current:
                self._paths[(self.site.key, query.path())] = served
                return self.search(query, page, check=check)
            raise FiltersIgnoredError(dropped)
        if query.zip and result.location is None:
            raise LocationNotFoundError(query.zip)
        return result

    def iter_pages(
        self,
        query: Query | None = None,
        *,
        max_pages: int | None = None,
        start_page: int = 1,
        first: SearchPage | None = None,
        budget: Callable[[], bool] = lambda: True,
    ) -> Iterator[SearchPage]:
        """Pages of results, from ``start_page`` until the last page (or ``max_pages``)."""
        page_no = start_page
        fetched = 0
        while True:
            if first is not None and page_no == start_page:
                page = first
            elif budget():
                page = self.search(query, page_no)
            else:
                return
            fetched += 1
            yield page
            last = min(page.pages or page_no, MAX_PAGES)
            if not page.listings or page_no >= last:
                return
            if max_pages is not None and fetched >= max_pages:
                return
            page_no += 1

    def iter_listings(
        self,
        query: Query | None = None,
        *,
        max_pages: int | None = 1,
        max_results: int | None = None,
        organic_only: bool = False,
        split_by_price: bool = False,
        max_requests: int | None = None,
    ) -> Iterator[Listing]:
        """Listings across pages, each car once (deduplicated by listing ID).

        Args:
            max_pages: Pages to read (per price band with ``split_by_price``);
                ``None`` reads to the end (up to AutoScout24's 200-page cap).
            max_results: Stop after this many listings.
            organic_only: Skip sponsored placements.
            split_by_price: Get past the 4,000-car cap by splitting the price range
                into bands. Cars without a price ("price on request") are not
                in any band.
            max_requests: Stop once this many API requests were made by this call.
        """
        start = self.requests

        def budget() -> bool:
            return max_requests is None or self.requests - start < max_requests

        if split_by_price:
            if not isinstance(query, SearchQuery):
                raise ValueError("split_by_price needs a SearchQuery (not a URL)")
            pages = self._iter_bands(query, max_pages, budget)
        else:
            pages = self.iter_pages(query, max_pages=max_pages, budget=budget)
        seen: set[str] = set()
        for page in pages:
            for listing in page.listings:
                if organic_only and listing.sponsored:
                    continue
                if listing.id in seen:
                    continue
                seen.add(listing.id)
                yield listing
                if max_results is not None and len(seen) >= max_results:
                    return

    def collect(self, query: Query | None = None, **kwargs: Any) -> list[Listing]:
        """:meth:`iter_listings` as a list."""
        return list(self.iter_listings(query, **kwargs))

    def _iter_bands(
        self, query: SearchQuery, max_pages: int | None, budget: Callable[[], bool]
    ) -> Iterator[SearchPage]:
        top = query.price_max if query.price_max is not None else PRICE_CEILING
        pending = [(query.price_min or 0, top)]
        while pending and budget():
            low, high = pending.pop(0)
            open_top = high == PRICE_CEILING and query.price_max is None
            band = query.with_prices(low or query.price_min, None if open_top else high)
            first = self.search(band, 1)
            if first.capped and high - low > 1:
                mid = split_price(low, high)
                pending[0:0] = [(low, mid), (mid + 1, high)]
                continue
            yield from self.iter_pages(band, max_pages=max_pages, first=first, budget=budget)

    # -- listing pages --------------------------------------------------------

    def details(self, id_or_url: str) -> ListingDetails:
        """Everything on one listing page. Accepts a listing ID or URL."""
        url = listing_url(id_or_url, self.site)
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        html = self.fetch(url, not_found=ListingNotFoundError)
        return parse_details(html, url, origin)

    # -- filter vocabulary ----------------------------------------------------

    def filter_options(self, make: str | None = None) -> FilterOptions:
        """Makes, models (for ``make``) and every option list of the site, in its language."""
        query = SearchQuery(make=make)
        url = search_url(query, 1, self.site)
        props = page_props(self.fetch(url))
        if make and not recognised_make(applied_filters(props)):
            raise UnknownMakeError(make, suggest(make, make_names(props)))
        return filter_options_from_props(props, self.site.key)
