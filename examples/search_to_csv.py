"""Export used BMW X1s in Germany (2019 or newer, up to EUR 30,000) to a CSV file.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/search_to_csv.py [pages]

Each page is one API request and holds up to 20 cars.
"""

from __future__ import annotations

import sys

from autoscout24_scraper import AutoScout24Scraper, SearchQuery
from autoscout24_scraper.export import write


def main() -> None:
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    scraper = AutoScout24Scraper()
    query = SearchQuery(
        make="bmw",
        model="x1",
        countries=["DE"],
        price_max=30_000,
        year_min=2019,
        sort="price",
    )
    cars = scraper.collect(query, max_pages=pages, organic_only=True)
    write(cars, "csv", "bmw_x1_de.csv")
    print(f"Saved {len(cars)} cars to bmw_x1_de.csv ({scraper.requests} requests)")
    for car in cars[:5]:
        print(
            f"  EUR {car.price or 0:>7,}  {car.first_registration}  {car.mileage_km or 0:>7,} km  "
            f"{car.fuel_type or '-':<16} {car.version or ''}"
        )


if __name__ == "__main__":
    main()
