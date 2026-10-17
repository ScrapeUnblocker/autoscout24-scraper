from __future__ import annotations

import argparse
import json

import pytest
from conftest import FakeClient, fixture_html

from autoscout24_scraper import AutoScout24Scraper, cli


def parse(*argv: str) -> argparse.Namespace:
    return cli.build_parser().parse_args(list(argv))


@pytest.mark.parametrize(
    "text, value", [("30000", 30000), ("30,000", 30000), ("30k", 30000), ("1.5m", 1_500_000)]
)
def test_amount(text, value):
    assert cli.amount(text) == value


def test_amount_rejects_junk():
    with pytest.raises(argparse.ArgumentTypeError):
        cli.amount("cheap")


def test_search_arguments_build_a_query():
    args = parse(
        "--site", "de", "search", "bmw", "x1",
        "--country", "DE,AT", "--price-max", "30k", "--year-min", "2019",
        "--km-max", "80k", "--fuel", "diesel,hybrid", "--gear", "automatic",
        "--body", "suv", "--seller", "dealer", "--power-min", "150", "--hp",
        "--zip", "80331", "--radius", "50", "--sort", "price", "--desc",
        "--param", "eq=37", "--pages", "0", "--organic-only",
    )  # fmt: skip
    assert args.site == "de"
    query = cli.query_from_args(args)
    assert (query.make, query.model) == ("bmw", "x1")
    assert query.countries == ["DE", "AT"]
    assert (query.price_max, query.km_max, query.year_min) == (30000, 80000, 2019)
    assert query.fuel == ["diesel", "hybrid"]
    assert (query.power_min, query.power_unit) == (150, "hp")
    assert (query.zip, query.radius_km) == ("80331", 50)
    assert (query.sort, query.descending) == ("price", True)
    assert query.extra == {"eq": "37"}
    assert args.pages == 0 and args.organic_only


def test_defaults():
    args = parse("search")
    query = cli.query_from_args(args)
    assert query.make is None and query.sort == "best" and query.descending is None
    assert args.pages == 1 and args.format == "json" and args.site == "com"
    assert parse("search", "--asc").descending is False


def test_bad_arguments_exit():
    with pytest.raises(SystemExit):
        parse("search", "--sort", "cheapest")
    with pytest.raises(SystemExit):
        parse("--site", "us", "search")
    with pytest.raises(SystemExit):
        parse("search", "--param", "novalue")


@pytest.fixture
def fake_scraper(monkeypatch):
    """Route the CLI to a scraper whose client answers from fixtures."""

    def responder(url, kw):
        if "/offers/" in url:
            return fixture_html("details_dealer.json")
        return fixture_html("search_bmw.json")

    client = FakeClient(responder)

    def make(args):
        return AutoScout24Scraper(client=client, site=args.site, sleep=lambda s: None)

    monkeypatch.setattr(cli, "make_scraper", make)
    return client


def test_main_search_writes_json(fake_scraper, capsys):
    assert cli.main(["search", "bmw", "--max", "2"]) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert [car["make"] for car in data] == ["BMW", "BMW"]
    assert "2 listings, 1 requests" in err
    assert fake_scraper.calls[0][0].startswith("https://www.autoscout24.com/lst/bmw?")


def test_main_search_to_csv_file(fake_scraper, tmp_path, capsys):
    out = tmp_path / "cars.csv"
    assert cli.main(["search", "bmw", "-f", "csv", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("id,url,title,make,model")


def test_main_details_and_filters(fake_scraper, capsys):
    assert cli.main(["details", "4856d9fc-5333-4c29-8ed2-0bd35c8e6422"]) == 0
    assert json.loads(capsys.readouterr().out)["power_kw"] == 225
    assert cli.main(["filters", "bmw", "-f", "table"]) == 0
    out = capsys.readouterr().out
    assert "[makes]" in out and "(3-series)" in out


def test_main_reports_errors(fake_scraper, capsys):
    assert cli.main(["search", "--url", "https://example.com/x", "bmw"]) == 1
    assert "error:" in capsys.readouterr().err
    assert cli.main(["search", "--radius", "10"]) == 1
    assert "radius_km needs a zip" in capsys.readouterr().err
