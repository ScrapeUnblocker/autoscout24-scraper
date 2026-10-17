"""Errors raised by the scraper."""

from __future__ import annotations


class AutoScout24Error(Exception):
    """Base class for scraper errors."""


class ParseError(AutoScout24Error):
    """The page came back without the data AutoScout24 normally embeds in it."""


class ListingNotFoundError(AutoScout24Error):
    """The listing does not exist (any more). AutoScout24 redirects sold cars to a search."""


class UnknownMakeError(AutoScout24Error, ValueError):
    """AutoScout24 did not recognise the make and would silently search every car."""

    def __init__(self, make: str, suggestions: list[str] | None = None):
        self.make = make
        self.suggestions = suggestions or []
        hint = f" Did you mean: {', '.join(self.suggestions)}?" if self.suggestions else ""
        super().__init__(
            f"AutoScout24 does not know the make {make!r}.{hint} "
            "Run `autoscout24-scraper filters` for every make."
        )


class UnknownModelError(AutoScout24Error, ValueError):
    """AutoScout24 did not recognise the model and would silently search the whole make."""

    def __init__(self, make: str, model: str, suggestions: list[str] | None = None):
        self.make = make
        self.model = model
        self.suggestions = suggestions or []
        hint = f" Did you mean: {', '.join(self.suggestions)}?" if self.suggestions else ""
        super().__init__(
            f"AutoScout24 does not know the {make} model {model!r}.{hint} "
            f"Run `autoscout24-scraper filters {make}` for every model."
        )


class FiltersIgnoredError(AutoScout24Error):
    """AutoScout24 answered with a page that does not apply some of the filters sent."""

    def __init__(self, dropped: dict[str, str]):
        self.dropped = dropped
        shown = ", ".join(f"{k}={v}" for k, v in dropped.items())
        super().__init__(
            f"AutoScout24 ignored these filters: {shown}. Check the values with "
            "`autoscout24-scraper filters`, or pass check=False to accept the page anyway."
        )


class LocationNotFoundError(AutoScout24Error, ValueError):
    """AutoScout24 could not place the postal code / city, so the radius would be ignored."""

    def __init__(self, zip_code: str):
        self.zip = zip_code
        super().__init__(
            f"AutoScout24 could not find the location {zip_code!r}. Use a postal code "
            "(e.g. 80331) or the city's local name (e.g. München), together with --country."
        )
