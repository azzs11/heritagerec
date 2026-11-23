"""Turn the official monument lists into one row per entry, checked against each list's own totals (0032).

Each parser reads a raw file from data/raw/coverage_audit_v1/ (see sources.py) and returns rows with the same
columns: list, list_id, name, locality, district, state, circle (ASI only), plus list-specific extras. A list's
rows are then compared with the totals the list itself states (per state and circle for ASI, per district or
zone for the state lists). A mismatch is reported, never patched over: the report says where the parser and the
list disagree.

Usage:
    uv run python -m src.coverage_audit.lists
Outputs:
    data/coverage_audit/lists_v1/<list>.csv      one row per entry
    results/coverage_audit/lists_v1.json, .md    counts and every check against the stated totals
"""

import bisect
import csv
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime

import pdfplumber
from bs4 import BeautifulSoup

from src.corpus.wikimedia import ROOT
from src.coverage_audit.sources import RAW_DIR, SOURCES, load_manifest, sha256

OUT_DIR = ROOT / "data/coverage_audit/lists_v1"
REPORT = ROOT / "results/coverage_audit/lists_v1"
COLUMNS = ["list", "list_id", "name", "locality", "district", "state", "circle", "page", "extra"]


def clean(text) -> str:
    return re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()


# ---------------------------------------------------------------- ASI


# The itemised pages spell a few states differently from the summary table on page 1; the summary's spelling
# is used everywhere.
ASI_STATE_SPELLING = {"N.C.T. of Delhi": "N.C.T. Delhi"}
# The summary table drops "Circle" from two names.
ASI_CIRCLE_SPELLING = {"Jabalpur": "Jabalpur Circle", "Raiganj": "Raiganj Circle"}


def asi_summary(pdf) -> dict:
    """Page 1: state -> {"total": n, "circles": {circle: n}}, and the stated grand total."""
    states, state, grand = {}, None, None
    for row in pdf.pages[0].extract_tables()[0][1:]:
        serial, name, total, circle, n = (clean(c) for c in row)
        n = int(re.sub(r"\D", "", n))
        if serial.upper() == "TOTAL":
            grand = n
            continue
        if name:
            state = name
            states[state] = {"total": int(total), "circles": {}}
        circle = ASI_CIRCLE_SPELLING.get(circle, circle)
        states[state]["circles"][circle] = n
    return {"states": states, "total": grand}


def _lines_outside(page, boxes) -> list[tuple[float, str]]:
    """Text lines of a page that are not inside any table, with their vertical position."""

    def outside(obj):
        return not any(
            b[0] - 1 <= obj["x0"] and obj["x1"] <= b[2] + 1 and b[1] - 1 <= obj["top"] and obj["bottom"] <= b[3] + 1
            for b in boxes
        )

    words = page.filter(outside).extract_words(keep_blank_chars=False)
    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w)
    out = []
    for top in sorted(lines):
        text = " ".join(w["text"] for w in sorted(lines[top], key=lambda w: w["x0"]))
        if not re.fullmatch(r"\d+", text):  # page numbers
            out.append((top, text))
    return out


def _heading(text: str, summary: dict, current: dict) -> None:
    """Update the current state and circle from a heading block."""
    m = re.search(r"jurisdiction of\s+(.*)$", text, re.I)
    if m:
        rest = m.group(1).strip()
        names = sorted(summary["states"], key=len, reverse=True)
        rest_norm = rest
        for wrong, right in ASI_STATE_SPELLING.items():
            rest_norm = rest_norm.replace(wrong, right)
        state = next((s for s in names if rest_norm.startswith(s)), None)
        if state is None:
            raise ValueError(f"unknown state heading: {text!r}")
        current["state"] = state
        circles = summary["states"][state]["circles"]
        # A one-circle state never repeats its circle; a several-circle state names the first circle after the
        # heading ("... (Bangalore Circle, Dharwad Circle and Hampi Circle) Bangalore Circle").
        current["circle"] = next(iter(circles)) if len(circles) == 1 else None
        tail = rest_norm[len(state) :]
        tail = re.sub(r"\(U\.T\.\)", "", tail)
        paren = re.match(r"^\s*\(([^)]*)\)", tail)
        if paren:
            # Odisha's heading names only its first circle: "Odisha (Bhubaneswar Circle)".
            only = ASI_CIRCLE_SPELLING.get(clean(paren.group(1)), clean(paren.group(1)))
            if only in circles:
                current["circle"] = only
        tail = re.sub(r"^\s*\([^)]*\)", "", tail).strip()
        if tail:
            _heading(tail, summary, current)
        return
    m = re.fullmatch(r"\(?\s*([A-Z][A-Za-z]+(?: Mini-)?\s*-?Circle)\s*\)?", text.strip())
    if m and current.get("state"):
        circle = ASI_CIRCLE_SPELLING.get(m.group(1), m.group(1))
        circle = {"Leh Mini-circle": "Leh Mini-Circle"}.get(circle, circle)
        if circle not in summary["states"][current["state"]]["circles"]:
            raise ValueError(f"circle {circle!r} is not listed for {current['state']}")
        current["circle"] = circle


def parse_asi(path) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        summary = asi_summary(pdf)
        current: dict = {"state": None, "circle": None}
        for pno, page in enumerate(pdf.pages, start=1):
            if pno <= 3:  # summary tables and the circle map
                continue
            tables = page.find_tables()
            events = [(top, "text", text) for top, text in _lines_outside(page, [t.bbox for t in tables])]
            for t in tables:
                for row_obj, cells in zip(t.rows, t.extract(), strict=True):
                    events.append((row_obj.bbox[1], "row", cells))
            events.sort(key=lambda e: e[0])
            block: list[str] = []
            for _, kind, value in events:
                if kind == "text":
                    block.append(value)
                    continue
                if block:
                    _heading(" ".join(block), summary, current)
                    block = []
                cells = [clean(c) for c in value] + [""] * 4
                serial, name, locality, district = cells[:4]
                if serial.startswith("Sl.No") or name.startswith("Name of the Monument"):
                    continue
                if not serial and rows and rows[-1]["state"] == current["state"]:
                    # A row broken over pages has no serial number on its rest; Fatehpur Sikri (Agra 33) runs
                    # over three pages.
                    prev = rows[-1]
                    for key, val in (("name", name), ("locality", locality), ("district", district)):
                        if val:
                            prev[key] = clean(f"{prev[key]} {val}")
                    continue
                if not current["state"] or not current["circle"]:
                    raise ValueError(f"row before any state or circle heading on page {pno}: {cells}")
                rows.append(
                    {
                        "list": "asi_cpm",
                        "serial": serial.rstrip("."),
                        "name": name,
                        "locality": locality,
                        "district": district,
                        "state": current["state"],
                        "circle": current["circle"],
                        "page": pno,
                    }
                )
            if block:
                _heading(" ".join(block), summary, current)
    for r in rows:
        r["list_id"] = f"asi:{r['state']}:{r['circle']}:{r['serial']}"
    return rows, summary


def check_asi(rows, summary) -> list[dict]:
    checks = []
    by_state = Counter(r["state"] for r in rows)
    by_circle = Counter((r["state"], r["circle"]) for r in rows)
    for state, info in summary["states"].items():
        checks.append({"what": f"state {state}", "stated": info["total"], "parsed": by_state.get(state, 0)})
        if len(info["circles"]) > 1:
            for circle, n in info["circles"].items():
                checks.append(
                    {"what": f"circle {state} / {circle}", "stated": n, "parsed": by_circle.get((state, circle), 0)}
                )
    checks.append({"what": "total", "stated": summary["total"], "parsed": len(rows)})
    dup = [k for k, n in Counter(r["list_id"] for r in rows).items() if n > 1]
    checks.append({"what": "repeated serial numbers within a circle", "stated": 0, "parsed": len(dup), "ids": dup})
    return checks


# ---------------------------------------------------------------- Karnataka (state list)

# Column order of every itemised table: taluk serial, taluk, locality, state serial, state monument, ASI serial,
# ASI monument, G.O. numbers. Each column edge is drawn as a group of two or three lines.
KA_SL, KA_TALUK, KA_LOCALITY, KA_STATE_SL, KA_STATE_NAME, KA_ASI_SL, KA_ASI_NAME, KA_GO = range(8)
KA_HEADER_WORDS = {"TALUK", "LOCALITY", "STATE", "MONUMENTS", "A.S.I.", "G.O", "SL", "SL.", "NO.", "NUMBERS"}
# The itemised pages and the district summary (pages 2-5) spell districts differently; this maps the itemised
# heading to the summary's name so the two can be compared. Spelling only, no merging.
KA_SUMMARY_NAME = {
    "Bangalore Urban": "Bangalore City",
    "Kolar": "Kolara",
    "Chikkaballapura": "Chikkaballapur",
    "Belagam": "Belgaum",
    "Bijapur": "Vijayapura",
    "Gulbarga": "Kalaburgi",
    "Yadgiri": "Yadagiri",
    "Chikkamagalur": "Chikmagalur",
    "Davanagere": "Davangere",
}


def _groups(values, tol):
    out: list[list[float]] = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return out


def _words_in(words, box):
    x0, top, x1, bottom = box
    return [
        w
        for w in words
        if x0 - 1 <= w["x0"] and w["x1"] <= x1 + 1 and top - 1 <= w["top"] and w["bottom"] <= bottom + 1
    ]


def ka_summary(pdf) -> dict:
    """Pages 2-5: district -> stated number of state-protected monuments."""
    stated = {}
    for page in pdf.pages[1:5]:
        for table in page.extract_tables():
            for row in table:
                cells = [clean(c) for c in row if c not in (None, "")]
                if len(cells) >= 3 and cells[0].isdigit() and cells[2].isdigit() and not cells[1].isdigit():
                    stated[cells[1]] = int(cells[2])
    return stated


def _ka_district_marks(page, words, boxes) -> list[tuple[float, str]]:
    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w)
    marks = []
    for top, ws in lines.items():
        text = clean(" ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])))
        m = re.search(r"(?:DIVISION, )?([A-Za-z][A-Za-z .]+?) DISTRICT$", text, re.I)
        # One heading (Chikkaballapura, page 52) has no "DISTRICT": an all-capitals line opening a table.
        bare = (
            re.fullmatch(r"[A-Z][A-Z .]{3,}", text)
            and not set(text.split()) & KA_HEADER_WORDS
            and any(abs(top - b[1]) < 25 for b in boxes)
        )
        if m or bare:
            marks.append((top, (m.group(1) if m else text).title()))
    return sorted(marks)


def parse_karnataka(path) -> tuple[list[dict], dict]:
    entries: list[dict] = []
    subtotals: list[dict] = []
    notes: list[str] = []
    district, last = None, {"taluk": "", "locality": ""}
    with pdfplumber.open(path) as pdf:
        stated = ka_summary(pdf)
        for pno, page in enumerate(pdf.pages, start=1):
            if pno <= 7:  # summary statements
                continue
            words = page.extract_words()
            boxes = sorted((t.bbox for t in page.find_tables()), key=lambda b: b[1])
            # Sub-tables drawn inside a cell repeat words of the outer table.
            boxes = [
                b
                for b in boxes
                if not any(
                    o != b and o[0] <= b[0] + 1 and o[1] <= b[1] + 1 and b[2] <= o[2] + 1 and b[3] <= o[3] + 1
                    for o in boxes
                )
            ]
            marks = _ka_district_marks(page, words, boxes)
            for idx, (x0, top, x1, bottom) in enumerate(boxes):
                # A first or last row with no horizontal rule of its own is left out of the table by pdfplumber
                # (page 43 starts with Tumkur 19); its vertical lines still reach the row's edge.
                vert = [e for e in page.edges if e["orientation"] == "v" and x0 - 2 <= e["x0"] <= x1 + 2]
                above = boxes[idx - 1][3] if idx else 0
                below = boxes[idx + 1][1] if idx + 1 < len(boxes) else page.height
                for _ in range(3):
                    top = min([e["top"] for e in vert if abs(e["bottom"] - top) <= 2 and e["top"] > above] + [top])
                    bottom = max(
                        [e["bottom"] for e in vert if abs(e["top"] - bottom) <= 2 and e["bottom"] < below] + [bottom]
                    )
                edges = _groups(
                    [
                        e["x0"]
                        for e in vert
                        if top - 2 <= e["top"] and e["bottom"] <= bottom + 2 and e["bottom"] - e["top"] > 3
                    ],
                    12,
                )
                inside = _words_in(words, (x0, top, x1, bottom))
                if len(edges) != 9:
                    if inside:
                        notes.append(f"page {pno}: a table with {len(edges)} column edges was skipped")
                    continue
                cols = [(max(edges[k]), min(edges[k + 1])) for k in range(8)]
                col_words: list[list[dict]] = [[] for _ in range(8)]
                for w in inside:
                    cx = (w["x0"] + w["x1"]) / 2
                    for k, (a, b) in enumerate(cols):
                        if a - 3 <= cx <= b + 3:
                            col_words[k].append(w)
                            break
                # Row bands: the rules crossing the state-serial column. Names wrap above and below their serial,
                # so a cell is everything between two rules, not a text line.
                mid = sum(cols[KA_STATE_SL]) / 2
                rules = [
                    e["top"]
                    for e in page.edges
                    if e["orientation"] == "h" and e["x0"] <= mid <= e["x1"] and top - 2 <= e["top"] <= bottom + 2
                ]
                ys = [sum(g) / len(g) for g in _groups(rules, 3)]
                if not ys or ys[0] > top + 3:
                    ys = [top, *ys]
                if ys[-1] < bottom - 3:
                    ys.append(bottom)
                # Each word goes to exactly one band, the one holding its centre: some cells are crossed by
                # short rules a few points apart (Bidar, page 152), and a tolerance would put a word in two bands.
                band_words: dict[tuple[int, int], list[dict]] = {}
                for k in range(8):
                    for w in col_words[k]:
                        band = min(max(bisect.bisect_right(ys, (w["top"] + w["bottom"]) / 2) - 1, 0), len(ys) - 2)
                        band_words.setdefault((band, k), []).append(w)
                for band, (y0, y1) in enumerate(zip(ys, ys[1:], strict=False)):
                    cells = []
                    for k in range(8):
                        ws = sorted(band_words.get((band, k), []), key=lambda w: (round(w["top"]), w["x0"]))
                        cells.append(clean(" ".join(w["text"] for w in ws)))
                    heading_band = False
                    for mark_top, mark_name in marks:
                        if mark_top <= y1:
                            district = mark_name
                            # A heading drawn inside the table ("UDUPI DISTRICT", page 19) fills a band of its
                            # own; it must not be read as the rest of the previous name.
                            heading_band = heading_band or mark_top >= y0 - 1
                    if heading_band:
                        continue
                    if "Taluk" in cells[KA_TALUK] or "Taluk" in cells[KA_SL]:
                        subtotals.append({"district": district, "stated": cells[KA_STATE_SL], "page": pno})
                        continue
                    if cells[KA_TALUK] not in ("", "-", "--", "TALUK"):
                        last["taluk"] = cells[KA_TALUK]
                    if cells[KA_LOCALITY] not in ("", "-", "--", "LOCALITY"):
                        last["locality"] = cells[KA_LOCALITY]
                    serial = cells[KA_STATE_SL]
                    name = cells[KA_STATE_NAME]
                    if re.fullmatch(r"\d+", serial):
                        entries.append(
                            {
                                "district": district,
                                "serial": serial,
                                "name": "" if name in ("-", "--") else name,
                                "locality": last["locality"],
                                "taluk": last["taluk"],
                                "go": cells[KA_GO],
                                "page": pno,
                            }
                        )
                    elif (
                        name
                        and name not in ("-", "--")
                        and not set(name.split()) & KA_HEADER_WORDS
                        and not serial
                        and not cells[KA_ASI_SL]
                        and entries
                        and entries[-1]["district"] == district
                    ):
                        # The rest of a name broken over a page or a rule.
                        entries[-1]["name"] = clean(f"{entries[-1]['name']} {name}")
    # Mandya's section is printed twice (pages 14-18 and 32-36). A repeat of the same district, serial and name
    # is dropped and counted.
    seen, kept, repeats = set(), [], []
    for e in entries:
        key = (e["district"], e["serial"], e["name"])
        if key in seen:
            repeats.append(e)
            continue
        seen.add(key)
        kept.append(e)
    rows = [
        {
            "list": "karnataka_state",
            "list_id": f"ka:{e['district']}:{e['serial']}",
            "name": e["name"],
            "locality": e["locality"],
            "district": e["district"],
            "state": "Karnataka",
            "circle": "",
            "page": e["page"],
            "extra": json.dumps({"taluk": e["taluk"], "go": e["go"]}, ensure_ascii=False),
        }
        for e in kept
    ]
    info = {"stated": stated, "subtotals": subtotals, "repeats": repeats, "notes": notes}
    return rows, info


def check_karnataka(rows, info) -> list[dict]:
    checks = []
    parsed = Counter(r["district"] for r in rows)
    for district, n in sorted(parsed.items()):
        summary_name = KA_SUMMARY_NAME.get(district, district)
        sub = [s["stated"] for s in info["subtotals"] if s["district"] == district]
        checks.append(
            {
                "what": f"district {district}",
                "stated": info["stated"].get(summary_name),
                "stated_subtotal": ", ".join(sub),
                "parsed": n,
            }
        )
    named = {KA_SUMMARY_NAME.get(d, d) for d in parsed}
    for district, n in info["stated"].items():
        if district not in named:
            checks.append({"what": f"district {district}", "stated": n, "stated_subtotal": "", "parsed": 0})
    checks.append({"what": "total", "stated": sum(info["stated"].values()), "parsed": len(rows)})
    checks.append(
        {"what": "repeated entries dropped (Mandya printed twice)", "stated": 0, "parsed": len(info["repeats"])}
    )
    empty = [r["list_id"] for r in rows if not r["name"]]
    checks.append({"what": "entries with a serial but no name", "stated": 0, "parsed": len(empty), "ids": empty})
    for district in parsed:
        serials = sorted(int(r["list_id"].rsplit(":", 1)[1]) for r in rows if r["district"] == district)
        gaps = sorted(set(range(1, serials[-1] + 1)) - set(serials))
        if gaps:
            checks.append(
                {
                    "what": f"serial numbers missing from the listing, {district}",
                    "stated": 0,
                    "parsed": len(gaps),
                    "ids": gaps,
                }
            )
    return checks


# ---------------------------------------------------------------- Madhya Pradesh (state list)


def parse_mp(path) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    table = soup.find_all("table")[0]
    header = [clean(c.get_text(" ")) for c in table.find("tr").find_all(["th", "td"])]
    expected = [
        "Sl.No.",
        "Name of Monument",
        "District",
        "Place and Tehsil",
        "Zone",
        "Period (Century)",
        "Monument Category",
    ]
    if header != expected:
        raise ValueError(f"unexpected MP header {header}")
    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = [clean(td.get_text(" ")) for td in tr.find_all("td")]
        if len(cells) != 7:
            continue
        serial, name, district, place, zone, period, category = cells
        rows.append(
            {
                "list": "mp_state",
                "list_id": f"mp:{serial}",
                "name": name,
                "locality": place,
                "district": district,
                "state": "Madhya Pradesh",
                "circle": "",
                "page": "",
                "extra": json.dumps({"zone": zone, "period": period, "category": category}, ensure_ascii=False),
            }
        )
    return rows, {}


def check_mp(rows) -> list[dict]:
    serials = [int(r["list_id"].split(":")[1]) for r in rows]
    gaps = sorted(set(range(1, max(serials) + 1)) - set(serials))
    return [
        # The page states no total; its serial numbers are the only count it gives.
        {"what": "rows against the last serial number", "stated": max(serials), "parsed": len(rows)},
        {"what": "serial numbers missing", "stated": 0, "parsed": len(gaps), "ids": gaps},
        {"what": "repeated serial numbers", "stated": 0, "parsed": len(serials) - len(set(serials))},
        {"what": "rows with no name", "stated": 0, "parsed": sum(1 for r in rows if not r["name"])},
    ]


# ---------------------------------------------------------------- UNESCO intangible heritage (India)


def parse_unesco(path) -> tuple[list[dict], dict]:
    """The "Listing of ICH" box of UNESCO's India page: every inscribed element, with its year and list.

    Ongoing nominations are shown in the same box but are not inscribed, so they are left out.
    """
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    heading = next(h for h in soup.find_all("h2") if "Listing of ICH" in h.get_text())
    box = heading.find_parent(["section", "div"])
    text = box.get_text(" | ", strip=True)
    stated = re.search(r"(\d+) elements? inscribed", text)
    ongoing = text.split("On-going nomination", 1)[1] if "On-going nomination" in text else ""
    rows, seen = [], set()
    for a in box.find_all("a", href=True):
        m = re.search(r"/en/(RL|USL|BSP)/.*-(\d{5})$", a["href"])
        name = clean(a.get_text(" "))
        if not m or a["href"] in seen or (ongoing and name in ongoing and name not in text.split("On-going")[0]):
            continue
        seen.add(a["href"])
        rows.append(
            {
                "list": "unesco_ich_india",
                "list_id": f"ich:{m.group(2)}",
                "name": name,
                "locality": "",
                "district": "",
                "state": "",
                "circle": "",
                "page": "",
                "extra": json.dumps({"list": m.group(1), "url": a["href"]}, ensure_ascii=False),
            }
        )
    return rows, {"stated": int(stated.group(1)) if stated else None}


# ---------------------------------------------------------------- run


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def write_csv(name: str, rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    manifest = load_manifest()
    for key, src in SOURCES.items():
        path = RAW_DIR / src["file"]
        if key not in manifest or not path.exists() or sha256(path) != manifest[key]["sha256"]:
            raise SystemExit(f"{key}: raw file missing or changed; run src.coverage_audit.sources first")

    asi_rows, asi_summary_info = parse_asi(RAW_DIR / SOURCES["asi_cpm"]["file"])
    for r in asi_rows:
        r["extra"] = json.dumps({"serial": r.pop("serial")})
    ka_rows, ka_info = parse_karnataka(RAW_DIR / SOURCES["karnataka_state"]["file"])
    mp_rows, _ = parse_mp(RAW_DIR / SOURCES["mp_state"]["file"])
    ich_rows, ich_info = parse_unesco(RAW_DIR / SOURCES["unesco_ich_india"]["file"])
    lists = {
        "asi_cpm": (asi_rows, check_asi(asi_rows, asi_summary_info)),
        "karnataka_state": (ka_rows, check_karnataka(ka_rows, ka_info)),
        "mp_state": (mp_rows, check_mp(mp_rows)),
        "unesco_ich_india": (
            ich_rows,
            [{"what": "elements inscribed", "stated": ich_info["stated"], "parsed": len(ich_rows)}],
        ),
    }
    for name, (rows, _) in lists.items():
        write_csv(name, rows)

    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_commit(),
        "sources": {k: {f: manifest[k].get(f) for f in ("url", "fetched", "sha256", "last_modified")} for k in SOURCES},
        "lists": {
            name: {
                "rows": len(rows),
                "checks": checks,
                "mismatches": sum(1 for c in checks if c["stated"] is not None and c["stated"] != c["parsed"]),
            }
            for name, (rows, checks) in lists.items()
        },
        "karnataka_notes": ka_info["notes"],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    REPORT.with_suffix(".md").write_text(markdown(report))
    for name, info in report["lists"].items():
        print(f"{name}: {info['rows']} rows, {info['mismatches']} checks differ from the list's own figures")


def markdown(report: dict) -> str:
    out = [
        "# Coverage audit: official lists parsed into rows",
        "",
        f"Generated by `src/coverage_audit/lists.py` on {report['generated'][:10]} at commit `{report['commit']}` "
        "(decision 0032). Every check compares the parsed rows with a figure the list itself states. A difference "
        "is reported here and never patched over.",
        "",
        "| List | Source | Fetched | SHA-256 | Rows |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, src in report["sources"].items():
        out.append(
            f"| {name} | {src['url']} | {src['fetched']} | `{src['sha256'][:12]}` | {report['lists'][name]['rows']} |"
        )
    for name, info in report["lists"].items():
        out += ["", f"## {name}", "", "| Check | Stated | Parsed | Note |", "| --- | --- | --- | --- |"]
        for c in info["checks"]:
            stated = "" if c["stated"] is None else c["stated"]
            note = []
            if c.get("stated_subtotal"):
                note.append(f"subtotal printed in the itemised list: {c['stated_subtotal']}")
            if c.get("ids"):
                note.append("ids: " + ", ".join(map(str, c["ids"][:20])) + (" …" if len(c["ids"]) > 20 else ""))
            flag = "" if c["stated"] is None or c["stated"] == c["parsed"] else " **differs**"
            out.append(f"| {c['what']} | {stated} | {c['parsed']}{flag} | {'; '.join(note)} |")
    if report["karnataka_notes"]:
        out += ["", "Karnataka parser notes:", ""] + [f"- {n}" for n in report["karnataka_notes"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
