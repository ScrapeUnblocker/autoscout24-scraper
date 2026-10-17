"""``autoscout24-scraper`` command line interface."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .export import FORMATS, write
from .urls import (
    BODIES,
    COLORS,
    COUNTRIES,
    FUELS,
    GEARS,
    OFFERS,
    SELLERS,
    SITES,
    SORTS,
    SearchQuery,
)

EXAMPLES = """\
examples:
  autoscout24-scraper search bmw x1 --country DE --price-max 30k --year-min 2019 -f table
  autoscout24-scraper search volkswagen golf --zip 80331 --radius 50 --sort distance
  autoscout24-scraper search --fuel electric --body suv --km-max 50k --pages 5 -f csv -o ev.csv
  autoscout24-scraper search porsche 911 --split-by-price --pages 0 --max-requests 60 -o 911.json
  autoscout24-scraper search --url "https://www.autoscout24.com/lst/audi/a4?atype=C&cy=D&fuel=D"
  autoscout24-scraper details 4856d9fc-5333-4c29-8ed2-0bd35c8e6422
  autoscout24-scraper filters bmw
"""


def amount(text: str) -> int:
    """``"30000"``, ``"30,000"``, ``"30k"`` or ``"1.5m"`` -> int."""
    value = text.strip().lower().replace(",", "").replace("_", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([km]?)", value)
    if not match:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}")
    factor = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2)]
    return int(round(float(match.group(1)) * factor))


def csv_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def key_value(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {text!r}")
    key, value = text.split("=", 1)
    return key.strip(), value.strip()


def _names(table: dict[str, Any]) -> str:
    return ", ".join(table)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoscout24-scraper",
        description="Scrape AutoScout24 car listings into JSON/CSV via the ScrapeUnblocker API.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--site",
        default="com",
        choices=list(SITES),
        help="AutoScout24 site; sets the label language (default: com, English)",
    )
    parser.add_argument("--proxy-country", help="route requests through this country")
    parser.add_argument("--retries", type=int, default=3, help="retries per request (default 3)")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="search car listings")
    search.add_argument("make", nargs="?", help="make name or slug, e.g. bmw, mercedes-benz")
    search.add_argument("model", nargs="?", help="model name or slug, e.g. x1, 3-series, c-class")
    search.add_argument("--url", help="a search URL copied from your browser (filters kept)")
    where = search.add_argument_group("location")
    where.add_argument(
        "--country",
        type=csv_list,
        default=[],
        help=f"ISO codes, comma-separated: {_names(COUNTRIES)}",
    )
    where.add_argument("--zip", help="postal code (or local city name) to search around")
    where.add_argument("--radius", type=int, help="radius around --zip in km")
    car = search.add_argument_group("car")
    car.add_argument("--price-min", type=amount)
    car.add_argument("--price-max", type=amount)
    car.add_argument("--year-min", type=int, help="first registration from (year)")
    car.add_argument("--year-max", type=int, help="first registration to (year)")
    car.add_argument("--km-min", type=amount)
    car.add_argument("--km-max", type=amount)
    car.add_argument("--power-min", type=int, help="in kW (or hp with --hp)")
    car.add_argument("--power-max", type=int, help="in kW (or hp with --hp)")
    car.add_argument("--hp", action="store_true", help="--power-min/--power-max are in hp")
    car.add_argument("--fuel", type=csv_list, default=[], help=_names(FUELS))
    car.add_argument("--gear", type=csv_list, default=[], help=_names(GEARS))
    car.add_argument("--body", type=csv_list, default=[], help=_names(BODIES))
    car.add_argument("--offer", type=csv_list, default=[], help=_names(OFFERS))
    car.add_argument("--color", type=csv_list, default=[], help=_names(COLORS))
    car.add_argument("--seller", choices=list(SELLERS))
    car.add_argument("--doors-min", type=int)
    car.add_argument("--seats-min", type=int)
    car.add_argument(
        "--param",
        type=key_value,
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="any other AutoScout24 URL parameter (repeatable)",
    )
    paging = search.add_argument_group("sorting and paging")
    paging.add_argument("--sort", default="best", choices=list(SORTS))
    order = paging.add_mutually_exclusive_group()
    order.add_argument("--desc", dest="descending", action="store_true", default=None)
    order.add_argument("--asc", dest="descending", action="store_false", default=None)
    paging.add_argument(
        "--pages", type=int, default=1, help="pages of 20 to read (0 = all, max 200); default 1"
    )
    paging.add_argument("--max", type=int, dest="max_results", help="stop after N listings")
    paging.add_argument("--organic-only", action="store_true", help="skip sponsored listings")
    paging.add_argument(
        "--split-by-price",
        action="store_true",
        help="get past the 4,000-listing cap by searching price bands",
    )
    paging.add_argument("--max-requests", type=int, help="stop after N API requests")
    _output_args(search, default="json")

    details = sub.add_parser("details", help="full details of one or more listings")
    details.add_argument("listings", nargs="+", metavar="ID_OR_URL")
    _output_args(details, default="json")

    filters = sub.add_parser("filters", help="makes, models and filter values of the site")
    filters.add_argument("make", nargs="?", help="also list this make's models")
    _output_args(filters, default="json")
    return parser


def _output_args(parser: argparse.ArgumentParser, default: str) -> None:
    parser.add_argument("-f", "--format", default=default, choices=FORMATS)
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")


def query_from_args(args: argparse.Namespace) -> SearchQuery:
    if args.model and not args.make:
        raise ValueError("a model needs a make")
    return SearchQuery(
        make=args.make,
        model=args.model,
        countries=args.country,
        zip=args.zip,
        radius_km=args.radius,
        price_min=args.price_min,
        price_max=args.price_max,
        year_min=args.year_min,
        year_max=args.year_max,
        km_min=args.km_min,
        km_max=args.km_max,
        power_min=args.power_min,
        power_max=args.power_max,
        power_unit="hp" if args.hp else "kw",
        fuel=args.fuel,
        gear=args.gear,
        body=args.body,
        seller=args.seller,
        offer=args.offer,
        color=args.color,
        doors_min=args.doors_min,
        seats_min=args.seats_min,
        sort=args.sort,
        descending=args.descending,
        extra=dict(args.param),
    )


def _filters_text(options: Any) -> str:
    data = options.to_dict()
    lines = []
    for key, values in data.items():
        if not isinstance(values, list) or not values:
            continue
        lines.append(f"[{key}]")
        for opt in values:
            slug = f"  ({opt['slug']})" if opt.get("slug") else ""
            lines.append(f"  {opt['value']:<10} {opt['label']}{slug}")
    return "\n".join(lines) + "\n"


def make_scraper(args: argparse.Namespace):
    from .scraper import AutoScout24Scraper

    return AutoScout24Scraper(
        site=args.site, proxy_country=args.proxy_country, max_retries=args.retries
    )


def run(args: argparse.Namespace) -> int:
    scraper = make_scraper(args)
    if args.command == "search":
        query: Any = args.url if args.url else query_from_args(args)
        if args.url and (args.make or args.split_by_price):
            raise ValueError("--url cannot be combined with MAKE/MODEL or --split-by-price")
        listings = scraper.collect(
            query,
            max_pages=None if args.pages == 0 else args.pages,
            max_results=args.max_results,
            organic_only=args.organic_only,
            split_by_price=args.split_by_price,
            max_requests=args.max_requests,
        )
        write(listings, args.format, args.output)
        print(f"{len(listings)} listings, {scraper.requests} requests", file=sys.stderr)
    elif args.command == "details":
        results = [scraper.details(item) for item in args.listings]
        write(results[0] if len(results) == 1 else results, args.format, args.output)
    elif args.command == "filters":
        options = scraper.filter_options(args.make)
        if args.format == "table":
            text = _filters_text(options)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as handle:
                    handle.write(text)
            else:
                sys.stdout.write(text)
        else:
            write(options, args.format, args.output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - report any failure as one clean line
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
