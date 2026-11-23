"""Tests for the open-licence image list (src/explorer/images.py) and the collection route."""

import gzip
import json

from fastapi.testclient import TestClient

from server.app import create_app
from src.explorer.images import OUT, cleveland_image, met_image


def test_only_open_met_images_are_kept():
    ok, why = met_image(
        {"isPublicDomain": True, "primaryImageSmall": "s.jpg", "primaryImage": "f.jpg", "creditLine": "Gift"}
    )
    assert why == "ok" and ok["thumb"] == "s.jpg" and ok["full"] == "f.jpg"
    assert ok["credit"] == "The Metropolitan Museum of Art · Gift"
    assert met_image({"isPublicDomain": False, "primaryImageSmall": "s.jpg"}) == (None, "not public domain")
    assert met_image({"isPublicDomain": True, "primaryImageSmall": ""}) == (None, "no image")


def test_only_cc0_cleveland_images_are_kept():
    item = {
        "share_license_status": "CC0",
        "images": {"web": {"url": "w.jpg", "width": "603", "height": "900"}, "print": {"url": "p.jpg"}},
        "creditline": "Gift",
        "url": "https://clevelandart.org/art/1",
    }
    ok, why = cleveland_image(item)
    assert why == "ok" and (ok["thumb"], ok["full"], ok["width"], ok["height"]) == ("w.jpg", "p.jpg", 603, 900)
    assert cleveland_image({**item, "share_license_status": "Copyrighted"}) == (None, "not CC0")
    assert cleveland_image({**item, "images": {}}) == (None, "no image")


def test_the_committed_list_holds_only_open_licences():
    rows = [json.loads(line) for line in gzip.open(OUT, "rt", encoding="utf-8")]
    assert rows and all(r["licence"] == "https://creativecommons.org/publicdomain/zero/1.0/" for r in rows)
    assert all(r["thumb"].startswith("https://") and r["credit"] for r in rows)
    assert len({r["doc_id"] for r in rows}) == len(rows)


def test_the_collection_route_pages_through_a_fixed_order():
    client = TestClient(create_app(use_keyword=False))
    first = client.get("/api/collection", params={"limit": 6}).json()
    again = client.get("/api/collection", params={"limit": 6}).json()
    nxt = client.get("/api/collection", params={"offset": 6, "limit": 6}).json()
    ids = [x["id"] for x in first["items"]]
    assert ids == [x["id"] for x in again["items"]] and len(ids) == 6
    assert not set(ids) & {x["id"] for x in nxt["items"]}
    assert all(x["image"]["thumb"] for x in first["items"])
    assert client.get("/api/collection", params={"limit": 0}).status_code == 422
