"""Draw the coverage-audit sample and build the author's matching sheet (decisions 0031, 0032).

The draw is seeded and stratified. Inside a stratum the ASI rows are allocated to circles or states in proportion
to their size (largest remainder), and each cell is a simple random sample, so every sampled entry carries its
inclusion probability. A seeded 10% of the sample is marked for a second check.

For every sampled entry the script asks Wikidata for up to five candidate items, by several searches tried in turn
(the name with the locality, the name without generic words, ASI-ID items mentioning the locality, items located
in the locality's own item, and a label search on the name). People, books and articles are filtered out. Every
search is saved untouched like any other Wikidata call, and the searches tried are written into the sheet so the
author can see what was already looked for.

Usage:
    uv run python -m src.coverage_audit.sample            (draw and sheet; about 20 minutes of polite API calls)
    uv run python -m src.coverage_audit.sample --limit 10 (first 10 entries only, to try it)
Outputs:
    results/coverage_audit/sample_v1.csv         the draw, with strata and inclusion probabilities
    results/coverage_audit/match_sheet_v1.csv    for the author: fill in `match` (a QID or none) and `searched`
    results/coverage_audit/sample_v1.md          allocation per stratum and cell
"""

import argparse
import csv
import random
import re
from collections import Counter

from src.corpus.wikimedia import ROOT, Wikimedia
from src.coverage_audit.lists import OUT_DIR as LISTS_DIR

SEED = 20261123
RESULTS = ROOT / "results/coverage_audit"
RAW = ROOT / "data/raw/coverage_audit_v1/wikidata"
API = "https://www.wikidata.org/w/api.php"
HINDI_BELT = ["Uttar Pradesh", "Madhya Pradesh", "Bihar", "Rajasthan"]
RECHECK_SHARE = 0.10
MAX_CANDIDATES = 5

# Strata of decision 0032: (name, list file, row filter, sample size, cell key or None for one cell).
STRATA = [
    ("karnataka_state", "karnataka_state", lambda r: bool(r["name"]), 75, None),
    ("karnataka_asi", "asi_cpm", lambda r: r["state"] == "Karnataka", 75, "circle"),
    ("hindi_belt_state", "mp_state", lambda r: bool(r["name"]), 50, None),
    ("hindi_belt_asi", "asi_cpm", lambda r: r["state"] in HINDI_BELT, 50, "state"),
    ("rest_asi", "asi_cpm", lambda r: r["state"] not in HINDI_BELT + ["Karnataka"], 50, "state"),
    ("unesco_ich", "unesco_ich_india", lambda r: True, None, None),  # every element
]

# The main language of each state's Wikipedia, for the local-language article column. A state left out has no
# single main language with a Wikipedia edition, and gets no local-language column.
LOCAL_LANGUAGE = {
    "Andhra Pradesh": "te",
    "Assam": "as",
    "Bihar": "hi",
    "Chhattisgarh": "hi",
    "Daman & Diu (U.T.)": "gu",
    "Goa": "gom",
    "Gujarat": "gu",
    "Haryana": "hi",
    "Himachal Pradesh": "hi",
    "Jharkhand": "hi",
    "Karnataka": "kn",
    "Kerala": "ml",
    "Madhya Pradesh": "hi",
    "Maharashtra": "mr",
    "N.C.T. Delhi": "hi",
    "Odisha": "or",
    "Puducherry (U.T.)": "ta",
    "Punjab": "pa",
    "Rajasthan": "hi",
    "Tamilnadu": "ta",
    "Telangana": "te",
    "Tripura": "bn",
    "Uttar Pradesh": "hi",
    "Uttarakhand": "hi",
    "West Bengal": "bn",
}

# State part of the monument codes in P1371 (N-KA-…, S-KA-…), only for states whose code was seen in the
# candidate data; a state left out is ranked by its name in the description alone.
STATE_CODE = {
    "Karnataka": "KA", "Madhya Pradesh": "MP", "Uttar Pradesh": "UP", "Bihar": "BR", "Rajasthan": "RJ",
    "Tamilnadu": "TN", "Maharashtra": "MH", "N.C.T. Delhi": "DL", "West Bengal": "WB", "Andhra Pradesh": "AP",
    "Gujarat": "GJ", "Kerala": "KL",
}  # fmt: skip

# Words that name a kind of monument rather than this monument; dropped for the second search.
GENERIC = {
    "temple", "temples", "the", "of", "and", "with", "in", "at", "on", "near", "its", "inscription", "inscriptions",
    "group", "ancient", "site", "sites", "remains", "ruined", "ruins", "old", "mound", "mounds", "monument",
    "monuments", "a", "an", "to", "together", "adjacent", "land", "sri", "shri", "known", "as", "called",
}  # fmt: skip
# Items of these classes are never the monument: human, book, written work, literary work, scholarly article.
NOT_A_MONUMENT = {"Q5", "Q571", "Q47461344", "Q7725634", "Q13442814", "Q3331189"}


def load_list(name: str) -> list[dict]:
    with open(LISTS_DIR / f"{name}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Largest-remainder allocation of n draws to cells in proportion to their sizes; ties go by cell name."""
    total = sum(sizes.values())
    quotas = {k: n * v / total for k, v in sizes.items()}
    out = {k: int(q) for k, q in quotas.items()}
    for k in sorted(quotas, key=lambda k: (-(quotas[k] - out[k]), k))[: n - sum(out.values())]:
        out[k] += 1
    return out


def draw() -> tuple[list[dict], list[dict]]:
    sample, allocation = [], []
    for stratum, list_name, keep, n, cell_key in STRATA:
        rows = sorted((r for r in load_list(list_name) if keep(r)), key=lambda r: r["list_id"])
        cells: dict[str, list[dict]] = {}
        for r in rows:
            cells.setdefault(r[cell_key] if cell_key else "all", []).append(r)
        share = {k: len(v) for k, v in cells.items()}
        sizes = share if n is None else allocate(share, n)
        for cell, members in sorted(cells.items()):
            k = len(members) if n is None else sizes[cell]
            # Each cell has its own generator, so changing one stratum never moves another's draw.
            picked = random.Random(f"{SEED}:{stratum}:{cell}").sample(members, k)
            allocation.append({"stratum": stratum, "cell": cell, "size": len(members), "drawn": k})
            for r in sorted(picked, key=lambda r: r["list_id"]):
                sample.append({**r, "stratum": stratum, "cell": cell, "inclusion_prob": round(k / len(members), 6)})
    for i, r in enumerate(sample, start=1):
        r["sample_id"] = f"cov{i:03d}"
        r["local_lang"] = LOCAL_LANGUAGE.get(r["state"], "")
    rechecks = set(random.Random(f"{SEED}:recheck").sample(range(len(sample)), round(RECHECK_SHARE * len(sample))))
    for i, r in enumerate(sample):
        r["recheck"] = "yes" if i in rechecks else ""
    return sample, allocation


# ---------------------------------------------------------------- Wikidata candidates


def search(wm: Wikimedia, text: str) -> list[str]:
    data = wm.get_json(
        "search",
        API,
        {"action": "query", "list": "search", "srsearch": text, "srlimit": 10, "srnamespace": 0, "format": "json"},
    )
    return [h["title"] for h in data.get("query", {}).get("search", [])]


def label_search(wm: Wikimedia, text: str) -> list[str]:
    data = wm.get_json(
        "wbsearch",
        API,
        {
            "action": "wbsearchentities",
            "search": text[:250],
            "language": "en",
            "limit": 10,
            "type": "item",
            "format": "json",
        },
    )
    return [h["id"] for h in data.get("search", [])]


def entities(wm: Wikimedia, qids: list[str]) -> dict:
    out = {}
    for i in range(0, len(qids), 50):
        batch = qids[i : i + 50]
        data = wm.get_json(
            "entities",
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|descriptions|claims",
                "languages": "en|hi|kn",
                "format": "json",
            },
        )
        out.update(data.get("entities", {}))
    return out


def claim_ids(entity: dict, prop: str) -> list[str]:
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        value = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        out.append(value["id"] if isinstance(value, dict) and "id" in value else str(value))
    return out


def core_words(name: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", name)
    return " ".join(w for w in words if w.lower() not in GENERIC)


def place_name(locality: str) -> str:
    # "Samalkot, (Bhimavaram)" -> "Samalkot"; brackets hold an alternative or a hamlet.
    return clean_place(re.split(r"[(,]", locality)[0])


def clean_place(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .-")


def located_in(wm: Wikimedia, place_qid: str) -> list[str]:
    rows = wm.sparql(
        "located_in",
        f"SELECT ?item WHERE {{ ?item wdt:P131 wd:{place_qid} . }} LIMIT 50",
    )
    return [r["item"].rsplit("/", 1)[-1] for r in rows]


SETTLEMENT = re.compile(r"^(village|town|city|census town|human settlement|taluk|tehsil|hobli|mandal|district)\b", re.I)


def place_item(wm: Wikimedia, place: str) -> str | None:
    """The Wikidata item of the entry's village or town: the first label match described as a settlement."""
    data = wm.get_json(
        "wbsearch",
        API,
        {
            "action": "wbsearchentities",
            "search": place,
            "language": "en",
            "limit": 10,
            "type": "item",
            "format": "json",
        },
    )
    for hit in data.get("search", []):
        if SETTLEMENT.match(hit.get("description", "")) and "India" in hit.get("description", "") + "India":
            return hit["id"]
    return None


def candidates(wm: Wikimedia, row: dict) -> tuple[list[str], list[str], str | None]:
    """Up to five candidate QIDs, the searches tried in order, and the item of the entry's place."""
    name = clean_place(row["name"])
    place = place_name(row["locality"])
    core = core_words(name)
    tried, found = [], []

    def add(label: str, qids: list[str]) -> None:
        tried.append(label)
        for q in qids:
            if q not in found:
                found.append(q)

    if row["list"] == "unesco_ich_india":
        # Intangible heritage has no place or monument code; UNESCO's titles are long, so the short name before
        # the first comma or colon is searched too ("Kutiyattam, Sanskrit theatre" -> "Kutiyattam").
        short = clean_place(re.split(r"[,:]", name)[0])
        add(f"label search '{short}'", label_search(wm, short))
        add(f"search '{short}'", search(wm, short))
        if short != name:
            add(f"label search '{name}'", label_search(wm, name))
        return found, tried, None
    place_qid = place_item(wm, place) if place else None
    if place:
        add(f"search '{name} {place}'", search(wm, f"{name} {place}"))
        if core and core.lower() != name.lower():
            add(f"search '{core} {place}'", search(wm, f"{core} {place}"))
        # P1371 carries both ASI codes (N-KA-…) and state-protected codes (S-KA-…).
        add(f"monument-ID items mentioning '{place}'", search(wm, f"{place} haswbstatement:P1371"))
    if core:
        add(f"monument-ID items matching '{core}'", search(wm, f"{core} haswbstatement:P1371"))
    if place_qid:
        add(f"items located in {place_qid} ('{place}')", located_in(wm, place_qid))
    add(f"label search '{name}'", label_search(wm, name))
    return found, tried, place_qid


def describe(entity: dict) -> str:
    labels, descs = entity.get("labels", {}), entity.get("descriptions", {})
    label = next((labels[lang]["value"] for lang in ("en", "hi", "kn") if lang in labels), "")
    desc = next((descs[lang]["value"] for lang in ("en", "hi", "kn") if lang in descs), "")
    asi = ", ".join(claim_ids(entity, "P1371"))
    parts = [entity["id"], label, desc]
    if asi:
        parts.append(f"ASI {asi}")
    parts.append(f"https://www.wikidata.org/wiki/{entity['id']}")
    return " | ".join(p for p in parts if p)


def rank(entity: dict, row: dict) -> int:
    """Higher for a candidate whose monument code or description points to the entry's own state or district."""
    codes = claim_ids(entity, "P1371")
    text = " ".join(d["value"] for d in entity.get("descriptions", {}).values()).lower()
    code = STATE_CODE.get(row["state"])
    score = 0
    if code and any(f"-{code}-" in c for c in codes):
        score += 2
    elif codes and code:
        score -= 2  # a monument code of another state
    for place in (row["district"], row["state"]):
        if place and place.lower().split(" (")[0] in text:
            score += 1
    return score


def keep_candidate(entity: dict) -> bool:
    if not entity or "missing" in entity:
        return False
    if set(claim_ids(entity, "P31")) & NOT_A_MONUMENT:
        return False
    # Villages and towns turn up through "located in"; they are the place, not the monument.
    descs = entity.get("descriptions", {})
    if any(SETTLEMENT.match(d["value"]) for d in descs.values()):
        return False
    countries = set(claim_ids(entity, "P17"))
    return not countries or "Q668" in countries


# ---------------------------------------------------------------- run


SAMPLE_COLUMNS = [
    "sample_id", "stratum", "cell", "inclusion_prob", "recheck", "list", "list_id", "name", "locality", "district",
    "state", "circle", "local_lang", "extra",
]  # fmt: skip
SHEET_COLUMNS = [
    "sample_id", "stratum", "list_id", "name", "locality", "district", "state", "place_item", "candidates", "match",
    "searched",
    "notes",
]  # fmt: skip


def write(path, columns, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only the first N sampled entries (a trial)")
    args = parser.parse_args()

    sample, allocation = draw()
    write(RESULTS / "sample_v1.csv", SAMPLE_COLUMNS, sample)
    by_stratum = Counter(r["stratum"] for r in sample)
    lines = [
        "# Coverage audit: the sample",
        "",
        f"Drawn by `src/coverage_audit/sample.py` with seed {SEED} from `data/coverage_audit/lists_v1/` (decision "
        f"0032): {len(sample)} entries, {sum(1 for r in sample if r['recheck'])} marked for a second check.",
        "",
        "| Stratum | Cell | Entries in the list | Drawn |",
        "| --- | --- | --- | --- |",
        *[f"| {a['stratum']} | {a['cell']} | {a['size']} | {a['drawn']} |" for a in allocation],
        "",
        "| Stratum | Drawn |",
        "| --- | --- |",
        *[f"| {k} | {v} |" for k, v in by_stratum.items()],
    ]
    (RESULTS / "sample_v1.md").write_text("\n".join(lines) + "\n")
    print(f"drew {len(sample)} entries")

    sheet_path = RESULTS / "match_sheet_v1.csv"
    if not args.limit and sheet_path.exists():
        with open(sheet_path, encoding="utf-8-sig") as f:
            filled = sum(1 for r in csv.DictReader(f) if (r.get("match") or "").strip())
        if filled:
            # The author's matches are hand work; a rerun must never write over them.
            print(f"kept {sheet_path.name}: {filled} entries already matched by the author")
            return
    rows = sample[: args.limit] if args.limit else sample
    wm = Wikimedia(RAW, pause=1.0)
    found_per_row = []
    for i, row in enumerate(rows, start=1):
        found, tried, place_qid = candidates(wm, row)
        row["place_item"] = f"https://www.wikidata.org/wiki/{place_qid}" if place_qid else ""
        found_per_row.append((found, tried))
        if i % 25 == 0:
            print(f"  searched {i} of {len(rows)}")
    every = sorted({q for found, _ in found_per_row for q in found})
    ents = entities(wm, every)
    sheet = []
    for row, (found, tried) in zip(rows, found_per_row, strict=True):
        kept = [q for q in found if keep_candidate(ents.get(q, {}))]
        # Stable sort: among equally ranked candidates the search order stands.
        kept = sorted(kept, key=lambda q: -rank(ents[q], row))[:MAX_CANDIDATES]
        sheet.append(
            {
                **row,
                "candidates": "\n".join(f"{n}) {describe(ents[q])}" for n, q in enumerate(kept, start=1)),
                "match": "",
                "searched": "auto: " + "; ".join(tried),
                "notes": "",
            }
        )
    name = "match_sheet_trial.csv" if args.limit else "match_sheet_v1.csv"
    write(RESULTS / name, SHEET_COLUMNS, sheet)
    with_any = sum(1 for s in sheet if s["candidates"])
    print(f"wrote {name}: {len(sheet)} entries, {with_any} with at least one candidate")
    print(f"Wikidata calls: {wm.fetched} fetched, {wm.reused} reused")


if __name__ == "__main__":
    main()
