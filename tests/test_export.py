from __future__ import annotations

import csv
import io
import json

import pytest
from conftest import fixture_html

from autoscout24_scraper.export import render, to_csv, to_table, write
from autoscout24_scraper.parsing import parse_details, parse_search_page

COM = "https://www.autoscout24.com"


@pytest.fixture(scope="module")
def cars():
    return parse_search_page(fixture_html("search_bmw.json"), "u", COM).listings


def test_json_and_jsonl(cars):
    data = json.loads(render(cars, "json"))
    assert data[0]["id"] == cars[0].id
    lines = render(cars, "jsonl").splitlines()
    assert len(lines) == len(cars)
    assert json.loads(lines[1])["price"] == cars[1].price


def test_csv_flattens_lists_and_dicts(cars):
    rows = list(csv.DictReader(io.StringIO(to_csv(cars))))
    assert len(rows) == len(cars)
    assert rows[0]["price"] == "20999"
    assert rows[0]["phones"] == "+493000000001 | +493000000002"
    details = parse_details(fixture_html("details_dealer.json"), "u", COM)
    row = next(csv.DictReader(io.StringIO(to_csv([details]))))
    assert json.loads(row["equipment"])["Safety & Security"][0] == "ABS"
    assert to_csv([]) == ""


def test_table(cars):
    table = to_table(cars)
    lines = table.splitlines()
    assert lines[0].split()[:3] == ["PRICE", "RATING", "REG"]
    assert "€20,999" in lines[1] and "good-price" in lines[1] and "138,000" in lines[1]
    assert "BMW 435" in lines[1]


def test_single_object_and_errors(cars, tmp_path):
    assert json.loads(render(cars[0], "json"))["id"] == cars[0].id
    with pytest.raises(ValueError):
        render(cars, "xml")
    path = tmp_path / "cars.csv"
    write(cars, "csv", str(path))
    text = path.read_text(encoding="utf-8")
    assert "Groß-Gerau" in text and "\r\n" not in text
    stream = io.StringIO()
    write(cars[:1], "jsonl", stream=stream)
    assert json.loads(stream.getvalue())["make"] == "BMW"
