# AutoScout24 Scraper

[![CI](https://github.com/ScrapeUnblocker/autoscout24-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/autoscout24-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-orange.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

Scrape **AutoScout24**, the pan-European online car marketplace, into clean JSON or CSV. It covers used and new car listings from Germany, Austria, Belgium, Spain, France, Italy, Luxembourg and the Netherlands, plus the full details of any listing. It ships as a CLI and a Python library.

**Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos).** Every page is fetched through the ScrapeUnblocker `getPageSource` API, which returns AutoScout24's fully rendered page, so you don't run a browser or manage blocks yourself.

```bash
autoscout24-scraper search bmw x1 --country DE --price-max 30k --year-min 2019 -f table
autoscout24-scraper search volkswagen golf --zip 80331 --radius 50 --sort distance -f csv -o golf.csv
autoscout24-scraper search --fuel electric --body suv --km-max 50k --sort newest --pages 5
autoscout24-scraper details 4856d9fc-5333-4c29-8ed2-0bd35c8e6422
autoscout24-scraper filters bmw
```

## Features

- **Search listings** with listing ID, make, model, model group, version, price in EUR, **AutoScout24's price rating** (`top-price`, `good-price`, `fair-price`, ...), previous price on reduced offers, mileage, first registration, fuel (site label plus a language-independent `fuel_type`), gearbox, power in kW and hp, consumption and CO2 text, offer type, damaged flag, dealer name, rating and review count, dealer phone numbers, country, postal code, city, distance from your search location, images, sponsored flag and URL.
- **Every main filter**: make and model (including model groups and lines such as `c-class` or `3-series`), countries, postal code plus radius, price, first-registration year, mileage, power (kW or hp), fuel, gearbox, body type, seller type (dealer or private), offer type (new, used, demo, classic, ...), colour, doors and seats. Any other AutoScout24 URL parameter can be passed straight through with `--param KEY=VALUE`.
- **Paste a search URL** from your browser with `--url` and its filters are kept.
- **8 sort orders**: best match, newest, price, mileage, year, power, distance, make. Ascending or descending.
- **Multi-page collection** (20 listings per page, up to AutoScout24's 200-page limit) with deduplication. `--organic-only` skips sponsored placements.
- **Past the 4,000-listing cap**: `--split-by-price` splits the price range into bands that each fit under AutoScout24's limit, then collects them one by one.
- **Full listing details** (`details`): body type, colour (plus the manufacturer's colour name), paint, upholstery, seats, doors, gears, cylinders, displacement, weight, drivetrain, combined consumption, CO2 g/km, electric range, EU emission class, German emission sticker, previous owners, accident and service-history flags, next inspection, **full equipment list by category**, the seller's description as plain text, net price and VAT rate, geolocation, full-size photos and the listing date.
- **19 AutoScout24 sites**: pick the label language with `--site` (`com`, `de`, `it`, `fr`, `es`, `nl`, `be-fr`, ...). `filters` lists every make, model and filter value of a site.
- **Robust**: retries with backoff on timeouts and transient errors. It also detects when AutoScout24 silently ignores your make, model, location or filters, and recovers or tells you, so you never get the wrong cars without knowing.
- Output as **JSON, JSON Lines, CSV or a terminal table**; typed dataclasses in Python.

## How it works

AutoScout24 is a Next.js site: every search and listing page embeds its full data as JSON (`<script id="__NEXT_DATA__">`). The scraper fetches the page through ScrapeUnblocker's [`getPageSource`](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) endpoint and reads that JSON directly. It uses no CSS selectors, so design changes don't break it, and you get the same structured data the page is built from. Each page fetch is one API request.

A few AutoScout24 behaviors the scraper handles for you:

- **Unknown makes, models and places are ignored silently.** AutoScout24 then shows *all* cars, the whole make, or results without a radius. Each search page echoes back the filters it applied. The scraper compares them with your request and raises `UnknownMakeError`, `UnknownModelError` (with "did you mean" suggestions) or `LocationNotFoundError` instead.
- **Model slugs differ per site.** The BMW 3 Series is `3-series` on autoscout24.com but `3er` on autoscout24.de. A slug that isn't the site's own is redirected *and loses its filters*. The scraper notices the dropped filters, repeats the request on the site's own slug (one extra request) and remembers it for later pages. If filters are still missing, it raises `FiltersIgnoredError`.
- **One search pages through at most 4,000 cars** (200 pages of 20). `split_by_price` / `--split-by-price` works around this. It cuts the price range at its geometric mean until every band reports 4,000 matches or fewer, then collects each band.
- **Sold cars redirect to a search page.** `details()` detects this and raises `ListingNotFoundError`.
- **Labels follow the site's language.** Fuel, gearbox and equipment names are translated by the site, so `fuel_type` is derived from AutoScout24's fuel code and is the same on every site.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/autoscout24-scraper.git
cd autoscout24-scraper
python -m pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) and expose it as `SCRAPEUNBLOCKER_KEY` (see `.env.example`):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here
```

Requires Python 3.9+. The only runtime dependency is the official [`scrapeunblocker`](https://docs.scrapeunblocker.com/sdks/python?utm_source=github&utm_medium=integration&utm_campaign=example-repos) SDK.

## CLI usage

```text
autoscout24-scraper [--site SITE] search  [MAKE [MODEL]] [filters] [--sort S] [--pages N] [-f FORMAT] [-o FILE]
autoscout24-scraper [--site SITE] search  --url SEARCH_URL [--pages N] ...
autoscout24-scraper [--site SITE] details ID_OR_URL [ID_OR_URL ...]
autoscout24-scraper [--site SITE] filters [MAKE]
```

### Search

```bash
# Used BMW X1, Germany only, max EUR 30,000, registered 2019 or later
autoscout24-scraper search bmw x1 --country DE --price-max 30k --year-min 2019 -f table

# Diesel automatic estates and SUVs from dealers in Germany and Austria, cheapest first, 5 pages
autoscout24-scraper search audi --country DE,AT --fuel diesel --gear automatic \
  --body station-wagon,suv --seller dealer --sort price --pages 5 -f csv -o audi.csv

# Cars within 50 km of a postal code, nearest first
autoscout24-scraper search volkswagen golf --country DE --zip 80331 --radius 50 --sort distance

# Every Porsche 911 on the site, past the 4,000 cap, spending at most 60 requests
autoscout24-scraper search porsche 911 --split-by-price --pages 0 --max-requests 60 -o 911.json

# A search you built in the browser, 3 pages
autoscout24-scraper search --url "https://www.autoscout24.com/lst/audi/a4?atype=C&cy=D&fuel=D" --pages 3
```

| Option | Meaning |
| --- | --- |
| `MAKE`, `MODEL` | Name or slug: `bmw`, `"Mercedes-Benz"`, `x1`, `c-class`, `3-series`, `id.3` (see `filters`) |
| `--country` | ISO codes, comma-separated: `DE,AT,BE,ES,FR,IT,LU,NL` (default: the site's own default) |
| `--zip`, `--radius` | Postal code (or the city's local name, e.g. `München`) and radius in km |
| `--price-min/max`, `--km-min/max` | Accept `30000`, `30,000` or `30k` |
| `--year-min/max` | First registration year |
| `--power-min/max`, `--hp` | Power in kW, or in hp with `--hp` |
| `--fuel` | `gasoline`, `diesel`, `electric`, `hybrid` (= hybrid-gasoline), `hybrid-diesel`, `lpg`, `cng`, `hydrogen`, `ethanol`, `other` |
| `--gear` | `automatic`, `manual`, `semi-automatic` |
| `--body` | `compact`, `convertible`, `coupe`, `suv`, `station-wagon`, `sedan`, `van`, `transporter`, `other` |
| `--seller` | `dealer` or `private` |
| `--offer` | `used`, `new`, `demo`, `pre-registered`, `employee`, `classic` |
| `--color` | `black`, `white`, `grey`, `silver`, `blue`, `red`, `green`, ... |
| `--doors-min`, `--seats-min` | Minimum doors / seats |
| `--param KEY=VALUE` | Any other AutoScout24 URL parameter (repeatable) |
| `--sort` | `best` (default), `newest`, `price`, `mileage`, `year`, `power`, `distance`, `make`; flip with `--desc` / `--asc` |
| `--pages N` | Pages of 20 to read (default 1, `0` = all) |
| `--max N` | Stop after N listings |
| `--organic-only` | Skip sponsored listings |
| `--split-by-price` | Collect past the 4,000-listing cap in price bands |
| `--max-requests N` | Hard limit on API requests for this run |
| `-f`, `-o` | `json` (default), `jsonl`, `csv` or `table`; output file |

### Listing details and filter values

```bash
autoscout24-scraper details 4856d9fc-5333-4c29-8ed2-0bd35c8e6422           # by listing ID
autoscout24-scraper details https://www.autoscout24.com/offers/bmw-435-...  # or by URL
autoscout24-scraper --site de details 4856d9fc-5333-4c29-8ed2-0bd35c8e6422  # German labels

autoscout24-scraper filters                 # every make with its slug, and every filter value
autoscout24-scraper filters bmw -f table    # plus BMW's models, model groups and lines
```

## Library usage

```python
from autoscout24_scraper import AutoScout24Scraper, SearchQuery

scraper = AutoScout24Scraper()  # reads SCRAPEUNBLOCKER_KEY; site="com" by default

query = SearchQuery(
    make="bmw",
    model="x1",
    countries=["DE"],
    price_max=30_000,
    year_min=2019,
    fuel=["diesel", "hybrid"],
    sort="price",
)

page = scraper.search(query)  # one page: listings + total + echo of filters
print(page.total, "matches;", len(page.listings), "on this page")

cars = scraper.collect(query, max_pages=5, organic_only=True)  # deduplicated
for car in cars[:3]:
    print(car.price, car.price_rating, car.mileage_km, car.first_registration, car.url)

details = scraper.details(cars[0].id)  # or a listing URL
print(details.power_kw, details.consumption_l_100km, details.equipment.keys())

everything = scraper.collect(
    SearchQuery(make="porsche", model="911"), split_by_price=True, max_pages=None, max_requests=60
)
```

`AutoScout24Scraper(site="de")` switches to German labels and autoscout24.de URLs. `proxy_country="DE"` routes requests through a country, and `max_retries` / `backoff` tune retries. Errors are importable from the package: `UnknownMakeError`, `UnknownModelError`, `LocationNotFoundError`, `FiltersIgnoredError`, `ListingNotFoundError`, `ParseError`.

## Example output

`autoscout24-scraper search bmw x1 --country DE --price-max 30k --year-min 2019 -f table` (first rows):

```text
PRICE    RATING      REG      KM       FUEL             KW   CAR                                           WHERE
€23,808  top-price   2020-11  36,666   hybrid-gasoline  162  BMW X1 xDrive25e Advantage / AHK/ Businesspa  DE Wunstorf
€27,480  fair-price  2022-09  41,077   hybrid-gasoline  162  BMW X1 xDrive25e  xLine LED Navi+ PA RFK DA+  DE Wuppertal
€14,750  top-price   2021-02  95,854   gasoline         100  BMW X1 sDrive 18 i xLine HUD Navi LED El. He  DE Steinfurt
€25,499  good-price  2021-07  45,324   hybrid-gasoline  162  BMW X1 xLine Panorama Kamera HUD DAB H K 19   DE Isernhagen
€24,577  top-price   2022-05  76,850   hybrid-gasoline  180  BMW X1 xDrive25e M Sport Head-Up+StHz+StKlim  DE Ansbach
€25,999  good-price  2022-02  65,137   diesel           110  BMW X1 Panorama Kamera DAB HiFi MSport Leder  DE Isernhagen
€26,480  fair-price  2020-08  52,300   diesel           140  BMW X1 xDrive 20 d Sport Line AHK Panorama L  DE Erfurt
```

One search result as JSON (excerpt; dealer contact fields redacted here):

```json
{
  "id": "77a8adf3-401b-4c20-8ecb-8f3ed5703e7a",
  "url": "https://www.autoscout24.com/offers/bmw-x1-xdrive-25-e-m-sport-electric-gasoline-white-cat_ma13mo19242-77a8adf3-401b-4c20-8ecb-8f3ed5703e7a",
  "title": "BMW X1",
  "make": "BMW",
  "model": "X1",
  "model_group": "X1",
  "version": "xDrive 25 e M Sport",
  "price": 11800,
  "currency": "EUR",
  "price_rating": "toolow-price",
  "previous_price": null,
  "mileage_km": 84000,
  "first_registration": "2024-05",
  "year": 2024,
  "fuel": "Electric/Gasoline",
  "fuel_type": "hybrid-gasoline",
  "transmission": "Automatic",
  "power_kw": 100,
  "power_hp": 136,
  "offer_type": "used",
  "damaged": true,
  "seller_type": "dealer",
  "dealer_name": "<dealer name>",
  "dealer_rating": 4.5,
  "dealer_reviews": 9,
  "phones": ["<dealer phone>"],
  "country": "DE",
  "zip": "89415",
  "city": "Lauingen",
  "image": "https://prod.pictures.autoscout24.net/listing-images/77a8adf3-...jpg/250x188.webp",
  "sponsored": false,
  "new_listing": false
}
```

`details` adds the full spec sheet (excerpt):

```json
{
  "status": "Active",
  "body_type": "Coupe",
  "price": 20999,
  "mileage_km": 138000,
  "first_registration": "2014-05",
  "transmission": "Automatic",
  "gears": 8,
  "cylinders": 6,
  "power_kw": 225,
  "power_hp": 306,
  "drivetrain": "4x4",
  "consumption_l_100km": 7.6,
  "co2_g_km": 178.0,
  "emission_class": "Euro 6",
  "emission_sticker": "4 (Green)",
  "body_color": "Red",
  "body_color_original": "MELBOURNEROT METALLIC",
  "upholstery": "Full leather",
  "seats": 4,
  "doors": 2,
  "non_smoking": true,
  "next_inspection": "06/2027",
  "equipment": {
    "Comfort & Convenience": ["Air conditioning", "Armrest", "Automatic climate control", "..."],
    "Safety & Security": ["ABS", "Adaptive Cruise Control", "Adaptive headlights", "..."]
  },
  "latitude": 49.91136,
  "longitude": 8.48803,
  "created_at": "2026-10-15T14:07:22.085Z"
}
```

`examples/compare_countries.py volkswagen golf` (one page per country):

```text
volkswagen golf, first registered 2020 or later, under 100,000 km
country   matches  sample  median EUR  median km  top/good
DE         10,596      20      16,822     66,758       95%
AT          1,407      20      18,740     64,774       75%
IT          2,463      20      20,200     68,150       70%
FR            695      20      20,985     66,920       58%
NL            987      20      22,820     58,814       65%
BE            713      20      18,600     76,182       55%
ES          1,498      20      21,018     62,638       65%
(7 requests)
```

(Live data from the day this README was written; your numbers will differ. The medians describe the sample collected, not the whole market.)

## Examples

| Script | What it does |
| --- | --- |
| [`examples/search_to_csv.py`](examples/search_to_csv.py) | Used BMW X1s in Germany under EUR 30,000 to CSV, cheapest first |
| [`examples/compare_countries.py`](examples/compare_countries.py) | Same model, seven countries: matches, median price and mileage, share rated top/good price |
| [`examples/listing_details.py`](examples/listing_details.py) | Newest electric SUVs with full details (range, power, equipment) saved to JSON |

## Sites

`--site` / `site=` picks the AutoScout24 site. All sites search the same inventory; the site sets the language of labels and URLs. When you don't pass `--country`, domestic sites search their own country and the international ones search all eight.

| Site key | Domain | Language | Default countries |
| --- | --- | --- | --- |
| `com` (default) | autoscout24.com | English | all 8 |
| `de`, `at` | autoscout24.de, .at | German | DE / AT |
| `it` | autoscout24.it | Italian | IT |
| `fr`, `lu` | autoscout24.fr, .lu | French | FR / LU |
| `es` | autoscout24.es | Spanish | ES |
| `nl` | autoscout24.nl | Dutch | NL |
| `be-fr`, `be-nl` | autoscout24.be/fr, /nl | French, Dutch | BE |
| `pl`, `ro`, `bg`, `cz`, `hu`, `hr`, `se`, `tr`, `ua` | autoscout24.pl, ... .com.ua | local | all 8 |

## Notes and limits

- **Requests:** each page or listing fetch is one API request. A search page holds up to 20 cars. A slug that the site redirects costs one extra request the first time.
- **4,000 per search:** without `--split-by-price`, results stop at 200 pages. Cars with no price ("price on request") fall outside every price band, so `--split-by-price` skips them.
- **Price rating** is AutoScout24's own label, shown on search results; listing pages don't carry it. `previous_price` is set only when the site shows a reduced price.
- **Privacy:** phone numbers and street addresses are kept for dealers only. Private sellers' contact details are deliberately not collected.
- **Sponsored listings** appear at the top of pages and can repeat across pages. They are flagged (`sponsored`) and deduplicated; `--organic-only` drops them.
- Scrape responsibly: collect public data at a reasonable rate and follow AutoScout24's terms and the laws that apply to you.

## Project layout

```text
autoscout24-scraper/
├── src/autoscout24_scraper/
│   ├── __init__.py      # public API + __version__
│   ├── scraper.py       # AutoScout24Scraper: fetch + retry, checks, paging, price bands
│   ├── parsing.py       # __NEXT_DATA__ -> Listing / ListingDetails / FilterOptions
│   ├── urls.py          # sites, filter vocabularies, SearchQuery -> URL
│   ├── models.py        # dataclasses
│   ├── errors.py        # exceptions
│   ├── export.py        # JSON / JSONL / CSV / table writers
│   └── cli.py           # `autoscout24-scraper` command
├── examples/            # runnable scripts
├── tests/               # offline tests (mocked client + trimmed real page data)
├── pyproject.toml
├── requirements.txt
├── Makefile
└── .env.example
```

## Development

```bash
make install   # pip install -e ".[dev]"
make lint      # ruff check . && ruff format --check .
make format    # ruff format .
make test      # pytest -q
```

The tests run fully offline. They use a fake client and trimmed snapshots of real AutoScout24 page data (dealer names, phone numbers and addresses replaced), so they cost no API credits. CI runs lint and tests on Python 3.9 and 3.12.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos): web scraping API that handles blocks, CAPTCHAs and rendering
- [Documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [Python SDK](https://docs.scrapeunblocker.com/sdks/python?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

## License

[MIT](LICENSE). Copyright (c) 2026 ScrapeUnblocker.
