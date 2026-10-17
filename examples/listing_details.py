"""Find the newest electric SUVs and pull the full listing page for each.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/listing_details.py [how-many]

Writes ev_suvs.json with the full details (equipment, consumption, battery range,
colour, previous owners, description, geolocation, ...) of each car.
"""

from __future__ import annotations

import sys

from autoscout24_scraper import AutoScout24Scraper, ListingNotFoundError, SearchQuery
from autoscout24_scraper.export import write


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    scraper = AutoScout24Scraper()
    query = SearchQuery(fuel=["electric"], body=["suv"], sort="newest", km_max=50_000)
    cars = scraper.collect(query, max_results=count, organic_only=True)
    details = []
    for car in cars:
        try:
            info = scraper.details(car.url)
        except ListingNotFoundError:  # sold between the search and now
            continue
        details.append(info)
        extras = sum(len(items) for items in info.equipment.values())
        price = f"EUR {info.price:,}" if info.price else "price on request"
        print(f"{info.make} {info.model} {info.version or ''}")
        print(
            f"  {price}  {info.first_registration}  {info.mileage_km or 0:,} km  "
            f"{info.power_kw} kW  range {info.electric_range_km or '-'} km  "
            f"{extras} equipment items"
        )
        print(f"  {info.city}, {info.country}  {info.url}")
    write(details, "json", "ev_suvs.json")
    print(f"Saved {len(details)} listings to ev_suvs.json ({scraper.requests} requests)")


if __name__ == "__main__":
    main()
