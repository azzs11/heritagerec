"""Open-licence images of museum objects, for the interface to show (decision 0025, redesign of 22 Nov 2026).

Reads each Met and Cleveland record's raw response (already on disk) for its image link, licence and credit line.
Only images the museum marks as open are kept: the Met's `isPublicDomain` and Cleveland's CC0 status. Nothing is
downloaded: the interface loads each image from the museum's own server, with its credit line and a link to the
museum's page. Art Institute of Chicago records were collected without their image ids, so they have none here.

Usage:
    uv run python -m src.explorer.images

Output:
    data/explorer/v1/images.jsonl.gz     doc_id, thumb, full, width, height, licence, credit, page, source
    results/explorer/images_v1.json      counts per source: records, with an open image, without, and why
"""

import gzip
import io
import json
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT

RECORDS = ROOT / "data/corpus_v1/records.jsonl.gz"
OUT = ROOT / "data/explorer/v1/images.jsonl.gz"
REPORT = ROOT / "results/explorer/images_v1.json"
SOURCES = ("met", "cleveland")
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"


def raw_item(path: str, frag: str, cache: dict) -> dict | None:
    if path not in cache:
        cache.clear()  # records of one file arrive together; keep one file in memory at a time
        cache[path] = json.load(gzip.open(ROOT / path, "rt", encoding="utf-8"))
    data = cache[path]
    if not frag:
        return data
    key, _, value = frag.partition("=")
    items = data.get("data") if isinstance(data.get("data"), list) else data.get("results") or []
    return next((it for it in items if str(it.get(key)) == value), None)


def met_image(it: dict) -> tuple[dict | None, str]:
    if not it.get("isPublicDomain"):
        return None, "not public domain"
    if not it.get("primaryImageSmall"):
        return None, "no image"
    return {
        "thumb": it["primaryImageSmall"],
        "full": it.get("primaryImage") or it["primaryImageSmall"],
        "width": None,
        "height": None,
        "licence": CC0,
        "credit": " · ".join(filter(None, ["The Metropolitan Museum of Art", it.get("creditLine")])),
        "page": it.get("objectURL"),
    }, "ok"


def cleveland_image(it: dict) -> tuple[dict | None, str]:
    if it.get("share_license_status") != "CC0":
        return None, "not CC0"
    web = (it.get("images") or {}).get("web") or {}
    if not web.get("url"):
        return None, "no image"
    full = ((it.get("images") or {}).get("print") or {}).get("url") or web["url"]
    return {
        "thumb": web["url"],
        "full": full,
        "width": int(web["width"]) if str(web.get("width", "")).isdigit() else None,
        "height": int(web["height"]) if str(web.get("height", "")).isdigit() else None,
        "licence": CC0,
        "credit": " · ".join(filter(None, ["The Cleveland Museum of Art", it.get("creditline")])),
        "page": it.get("url"),
    }, "ok"


def main() -> None:
    by_file = defaultdict(list)
    for line in gzip.open(RECORDS, "rt", encoding="utf-8"):
        r = json.loads(line)
        if r["source"] in SOURCES:
            path, _, frag = r["raw_ref"].partition("#")
            by_file[path].append((r["id"], r["source"], frag))
    counts = defaultdict(Counter)
    rows, cache = [], {}
    for path in sorted(by_file):
        for doc_id, source, frag in sorted(by_file[path]):
            it = raw_item(path, frag, cache)
            counts[source]["records"] += 1
            if it is None:
                counts[source]["raw item not found"] += 1
                continue
            image, why = (met_image if source == "met" else cleveland_image)(it)
            counts[source][why] += 1
            if image:
                rows.append({"doc_id": doc_id, "source": source, **image})
    rows.sort(key=lambda r: r["doc_id"])
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(buf.getvalue())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "images": len(rows),
        "by_source": {s: dict(sorted(c.items())) for s, c in sorted(counts.items())},
        "note": "Art Institute of Chicago records were collected without image ids and have no image here.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
