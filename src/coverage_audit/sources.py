"""Fetch the official monument lists for the coverage audit (decisions 0031, 0032).

Each list is saved untouched under data/raw/coverage_audit_v1/, and its URL, fetch time, size, SHA-256 and any
Last-Modified header go into a manifest there. A file already on disk is never fetched again: the version used
is the one in the manifest. A changed list means a new run directory, not an overwrite.

Usage:
    uv run python -m src.coverage_audit.sources
"""

import hashlib
import json
from datetime import UTC, datetime

import requests

from src.corpus.wikimedia import REPO_URL, ROOT

RAW_DIR = ROOT / "data/raw/coverage_audit_v1"
MANIFEST = RAW_DIR / "manifest.json"

# Madhya Pradesh's live page returned 404 on 23 Nov 2026, so the list is the Internet Archive's copy of
# 20 Oct 2021; the "id_" form returns the page as archived, without the Wayback toolbar.
SOURCES = {
    "asi_cpm": {
        "url": "https://asi.nic.in/pdf/CPM_List.pdf",
        "file": "asi_cpm_list.pdf",
        "publisher": "Archaeological Survey of India",
        "title": "List of Centrally Protected Monuments/Sites, state-wise and circle-wise",
    },
    "karnataka_state": {
        "url": "https://archaeology.karnataka.gov.in/storage/pdf-files/monument%20list%20final%20english.pdf",
        "file": "karnataka_monument_list_final_english.pdf",
        "publisher": "Department of Archaeology, Museums and Heritage, Government of Karnataka",
        "title": "Monument list (final, English)",
    },
    "mp_state": {
        "url": "http://web.archive.org/web/20211020112952id_/http://archaeology.mp.gov.in/en-us/Monuments/Protected-Monuments",
        "original_url": "http://archaeology.mp.gov.in/en-us/Monuments/Protected-Monuments",
        "archived": "2021-10-20T11:29:52Z",
        "file": "mp_protected_monuments_20211020.html",
        "publisher": "Directorate of Archaeology, Archives and Museums, Government of Madhya Pradesh",
        "title": "Protected Monuments",
    },
    "unesco_ich_india": {
        "url": "https://ich.unesco.org/en/state/india-IN",
        "file": "unesco_ich_india.html",
        "publisher": "UNESCO Intangible Cultural Heritage",
        "title": "India: elements inscribed on the Lists",
    },
}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def fetch_all() -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    session = requests.Session()
    session.headers["User-Agent"] = f"HeritageRec-CoverageAudit/1.0 ({REPO_URL})"
    for key, src in SOURCES.items():
        path = RAW_DIR / src["file"]
        if path.exists() and key in manifest:
            if sha256(path) != manifest[key]["sha256"]:
                raise SystemExit(f"{path.name} no longer matches its manifest hash; refusing to continue")
            print(f"{key}: kept {path.name}")
            continue
        r = session.get(src["url"], timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
        manifest[key] = {
            **src,
            "fetched": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bytes": len(r.content),
            "sha256": sha256(path),
            "last_modified": r.headers.get("Last-Modified"),
            "content_type": r.headers.get("Content-Type"),
        }
        print(f"{key}: fetched {path.name} ({len(r.content):,} bytes)")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


if __name__ == "__main__":
    fetch_all()
