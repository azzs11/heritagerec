"""Photographs of the graph's entities from Wikimedia Commons, with their credit and licence (decision 0034).

Each entity's Wikidata image (P18) is read from the core graph's saved responses (data/raw/graph_core_v1/). For each
file, the Commons API gives a thumbnail URL, the size, and the file's own credit: the artist and the licence
(`extmetadata`). Every response is saved untouched under data/raw/commons_v1/. Nothing is downloaded: the interface
loads each thumbnail from Commons and shows its credit wherever the photograph appears.

A file is kept only with a machine-readable licence (LicenseShortName and, except for public-domain files, a
LicenseUrl), so its credit can always be shown; every file left out is counted with its reason. Commons holds only
free files, so no NonCommercial licence can occur; a file with a recorded restriction (for example trademarks or
personality rights) is kept, and the restriction is carried with it.

Usage:
    uv run python -m src.explorer.commons_images
Output:
    data/explorer/v1/entity_images.jsonl.gz    entity, file, thumb, full, width, height, licence, licence_name,
                                               artist, credit, page, restrictions, source
    results/explorer/entity_images_v1.json      counts: entities with P18, kept, left out and why, by licence
"""

import gzip
import html
import io
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import quote

from src.corpus.wikimedia import ROOT, Wikimedia

RAW_GRAPH = ROOT / "data/raw/graph_core_v1"
RAW = ROOT / "data/raw/commons_v1"
OUT = ROOT / "data/explorer/v1/entity_images.jsonl.gz"
REPORT = ROOT / "results/explorer/entity_images_v1.json"
API = "https://commons.wikimedia.org/w/api.php"
THUMB_WIDTH = 400
BATCH = 50
# Commons answers 414 above about 8,000 characters of URL; the titles get 6,000 of them.
MAX_TITLE_CHARS = 6000


def p18_files() -> dict[str, str]:
    """Entity -> its first truthy P18 file name (preferred rank first, deprecated never)."""
    out = {}
    for path in sorted(RAW_GRAPH.glob("entities_*.json.gz")):
        for qid, entity in json.load(gzip.open(path, "rt", encoding="utf-8")).get("entities", {}).items():
            claims = [c for c in entity.get("claims", {}).get("P18", []) if c.get("rank") != "deprecated"]
            claims.sort(key=lambda c: c.get("rank") != "preferred")
            for c in claims:
                value = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(value, str) and value:
                    out[qid] = value
                    break
    return out


def plain(text: str | None) -> str:
    """Commons credit fields are HTML; the interface shows text."""
    if not text:
        return ""
    out = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()
    # Commons signatures carry the user's talk and contributions links: "Name (talk | contribs)".
    out = re.sub(r"\(\s*(talk|contribs)(\s*\|\s*(talk|contribs))*\s*\)", "", out, flags=re.I)
    out = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", out))
    return re.sub(r"\s+", " ", out).strip(" ·,;")


def first_sentence(text: str) -> str:
    """Up to the first full stop that ends a sentence: one after a lone capital is an initial ("Timothy A. Gonsalves")."""
    for m in re.finditer(r"[.!?](\s|$)", text):
        before = text[: m.start()]
        if re.search(r"(^|\s)[A-Z]$", before):
            continue
        return before.strip()
    return text.strip()


def short_artist(artist: str, limit: int = 80) -> str:
    """The name to credit under a photograph. A short field is the credit as it stands. Some Commons artist fields
    are long notes ("This Photo was taken by X. Feel free to use my photos, but please mention me..."): then the
    name after "taken by" when there is one, else the first sentence, cut to `limit`. The full field is kept as
    `artist_note` and stays on the file's Commons page, which every credit links to."""
    if len(artist) <= limit:
        return artist
    m = re.search(r"taken by (.+)", artist, flags=re.I)
    name = first_sentence(m.group(1) if m else artist)
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def image_record(page: dict) -> tuple[dict | None, str]:
    info = (page.get("imageinfo") or [None])[0]
    if page.get("missing") or not info:
        return None, "file missing on Commons"
    meta = info.get("extmetadata") or {}
    value = lambda key: (meta.get(key) or {}).get("value")  # noqa: E731
    name = plain(value("LicenseShortName"))
    url = value("LicenseUrl") or ""
    public_domain = name.lower().startswith(("public domain", "pd", "cc0"))
    if not name:
        return None, "no machine-readable licence"
    if not url and not public_domain:
        return None, "licence without a link"
    note = plain(value("Artist"))
    artist = short_artist(note) if note else ""
    credit = " · ".join(filter(None, [f"Photo: {artist}" if artist else "Photo: Wikimedia Commons", name]))
    return {
        "file": page["title"].removeprefix("File:"),
        "thumb": info.get("thumburl") or info["url"],
        "full": info["url"],
        "width": info.get("thumbwidth") or info.get("width"),
        "height": info.get("thumbheight") or info.get("height"),
        "licence": url,
        "licence_name": name,
        "artist": artist,
        "artist_note": note if note != artist else "",
        "credit": credit,
        "page": info.get("descriptionurl"),
        "restrictions": plain(value("Restrictions")),
        "source": "commons",
    }, "ok"


def batches(files: list[str], max_titles: int = BATCH, max_chars: int = MAX_TITLE_CHARS) -> list[list[str]]:
    """Up to 50 titles per request (the API's limit), fewer when long names would make the URL too long."""
    out: list[list[str]] = []
    size = 0
    for f in files:
        cost = len(quote(f"File:{f}")) + 3  # the encoded title and its separator
        if out and len(out[-1]) < max_titles and size + cost <= max_chars:
            out[-1].append(f)
            size += cost
        else:
            out.append([f])
            size = cost
    return out


def fetch(wm: Wikimedia, files: list[str]) -> dict[str, dict]:
    """File name -> the API's page for it, following the API's title normalisation."""
    pages = {}
    for batch in batches(files):
        data = wm.get_json(
            "imageinfo",
            API,
            {
                "action": "query",
                "titles": "|".join(f"File:{f}" for f in batch),
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata|mime",
                "iiurlwidth": THUMB_WIDTH,
                "format": "json",
                "formatversion": "2",
            },
        )
        query = data.get("query", {})
        back = {n["to"]: n["from"] for n in query.get("normalized", [])}
        for page in query.get("pages", []):
            asked = back.get(page["title"], page["title"]).removeprefix("File:")
            pages[asked] = page
    return pages


def main() -> None:
    files = p18_files()
    wm = Wikimedia(RAW, pause=1.0)
    unique = sorted(set(files.values()))
    pages = fetch(wm, unique)
    reasons: Counter = Counter()
    licences: Counter = Counter()
    buf = io.BytesIO()
    kept = restricted = 0
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for qid in sorted(files):
            page = pages.get(files[qid]) or pages.get(files[qid].replace("_", " "))
            rec, why = image_record(page) if page else (None, "no answer for the file")
            reasons[why] += 1
            if rec is None:
                continue
            kept += 1
            licences[rec["licence_name"]] += 1
            restricted += bool(rec["restrictions"])
            gz.write((json.dumps({"entity": qid, **rec}, ensure_ascii=False) + "\n").encode("utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(buf.getvalue())
    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "entities_with_p18": len(files),
        "distinct_files": len(unique),
        "kept": kept,
        "outcomes": dict(reasons),
        "by_licence": dict(licences.most_common()),
        "with_restrictions": restricted,
        "commons_requests": {"fetched": wm.fetched, "reused": wm.reused},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"{OUT.relative_to(ROOT)}: {kept} of {len(files)} entities with a P18 image; {dict(reasons)}")


if __name__ == "__main__":
    main()
