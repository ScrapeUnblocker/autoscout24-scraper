"""Compare asking prices for the same car across European countries.

Collects listings for one model in each country (same filters everywhere) and prints
the number of cars found, the median price, the median mileage and the share of cars
AutoScout24 rates as a "top" or "good" price.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/compare_countries.py [make] [model] [pages-per-country]
    python examples/compare_countries.py volkswagen golf 2

The figures describe the sample collected (pages x 20 cars per country), not the
whole market.
"""

from __future__ import annotations

import statistics
import sys

from autoscout24_scraper import AutoScout24Scraper, SearchQuery

COUNTRIES = ["DE", "AT", "IT", "FR", "NL", "BE", "ES"]


def main() -> None:
    make = sys.argv[1] if len(sys.argv) > 1 else "volkswagen"
    model = sys.argv[2] if len(sys.argv) > 2 else "golf"
    pages = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    scraper = AutoScout24Scraper()
    print(f"{make} {model}, first registered 2020 or later, under 100,000 km")
    row = "{:<8} {:>8} {:>7} {:>11} {:>10} {:>9}"
    print(row.format("country", "matches", "sample", "median EUR", "median km", "top/good"))
    for country in COUNTRIES:
        query = SearchQuery(
            make=make, model=model, countries=[country], year_min=2020, km_max=100_000
        )
        total, cars, seen = 0, [], set()
        for page in scraper.iter_pages(query, max_pages=pages):
            total = total or page.total or 0
            for car in page.listings:
                if car.price and not car.sponsored and car.id not in seen:
                    seen.add(car.id)
                    cars.append(car)
        if not cars:
            print(row.format(country, f"{total:,}", 0, "-", "-", "-"))
            continue
        price = statistics.median(c.price for c in cars)
        km = statistics.median(c.mileage_km or 0 for c in cars)
        rated = [c for c in cars if c.price_rating]
        good = sum(c.price_rating in ("top-price", "good-price") for c in rated)
        share = f"{good / len(rated):.0%}" if rated else "-"
        print(row.format(country, f"{total:,}", len(cars), f"{price:,.0f}", f"{km:,.0f}", share))
    print(f"({scraper.requests} requests)")


if __name__ == "__main__":
    main()
