"""Coverage of the audit sample on Wikidata, from the author's matches (decisions 0031, 0032).

Reads the author's matching sheet and, for every matched item, fetches what Wikidata holds about it: monument code
(P1371), labels and descriptions in English, Hindi, Kannada and the entry's local language, coordinates, image,
statement and sitelink counts, Wikipedia articles and their lengths. It adds whether the item is in corpus v1 (a
document is about it) and its degree in the core graph. Rates per stratum carry Wilson 95% intervals.

Entries the author has not matched yet are counted as pending and left out of every rate, so the script can be run
at any point; the report says how many are done.

It also compares the full ASI list with Wikidata: distinct monument codes per state (P1371, "N-KA-…" for ASI,
"S-KA-…" for state lists) against the ASI list's own per-state totals.

Usage:
    uv run python -m src.coverage_audit.fill
Outputs:
    results/coverage_audit/coverage_v1.csv        one row per sampled entry, with the fetched facts
    results/coverage_audit/coverage_v1.json, .md  rates per stratum, the full-list comparison, progress
"""

import argparse
import csv
import gzip
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from statsmodels.stats.proportion import proportion_confint

from src.corpus.wikimedia import ROOT, Wikimedia
from src.coverage_audit.lists import OUT_DIR as LISTS_DIR
from src.coverage_audit.sample import API, RAW, RESULTS

SHEET = RESULTS / "match_sheet_v1.csv"
SAMPLE = RESULTS / "sample_v1.csv"
OUT = RESULTS / "coverage_v1"
GRAPH_EDGES = ROOT / "data/graph/core_v1/edges.tsv.gz"
QID = re.compile(r"^Q\d+$")
LANGS = ["en", "hi", "kn"]
# The state part of P1371 codes, as found on Wikidata on 23 Nov 2026 (every ASI state has one).
CODE_STATE = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar", "CT": "Chhattisgarh",
    "DD": "Daman & Diu (U.T.)", "DL": "N.C.T. Delhi", "GA": "Goa", "GJ": "Gujarat", "HP": "Himachal Pradesh",
    "HR": "Haryana", "JH": "Jharkhand", "JK": "Jammu & Kashmir (U.T.)", "KA": "Karnataka", "KL": "Kerala",
    "LA": "Ladakh (U.T.)", "MH": "Maharashtra", "ML": "Meghalaya", "MN": "Manipur", "MP": "Madhya Pradesh",
    "MZ": "Mizoram", "NL": "Nagaland", "OR": "Odisha", "PB": "Punjab", "PY": "Puducherry (U.T.)",
    "RJ": "Rajasthan", "SK": "Sikkim", "TG": "Telangana", "TN": "Tamilnadu", "TR": "Tripura",
    "UP": "Uttar Pradesh", "UT": "Uttarakhand", "WB": "West Bengal",
}  # fmt: skip


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wilson(k: int, n: int) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return round(float(lo), 3), round(float(hi), 3)


def entities(wm: Wikimedia, qids: list[str]) -> dict:
    out = {}
    for i in range(0, len(qids), 50):
        data = wm.get_json(
            "fill_entities",
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(qids[i : i + 50]),
                "props": "labels|descriptions|claims|sitelinks",
                "format": "json",
            },
        )
        out.update(data.get("entities", {}))
    return out


def article_lengths(wm: Wikimedia, lang: str, titles: list[str]) -> dict[str, int]:
    """Page length in bytes for each title on one Wikipedia, following redirects."""
    out = {}
    for i in range(0, len(titles), 50):
        data = wm.wiki(
            "fill_lengths",
            {"action": "query", "prop": "info", "titles": "|".join(titles[i : i + 50]), "redirects": 1},
            lang=lang,
        )
        query = data.get("query", {})
        back = {r["to"]: r["from"] for r in query.get("redirects", [])}
        back.update({n["to"]: n["from"] for n in query.get("normalized", [])})
        for page in query.get("pages", []):
            if "length" in page:
                title = page["title"]
                out[back.get(title, title)] = page["length"]
    return out


def graph_facts() -> tuple[Counter, set]:
    degree, in_corpus = Counter(), set()
    with gzip.open(GRAPH_EDGES, "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            source, relation, target, *_ = line.rstrip("\n").split("\t")
            degree[source] += 1
            degree[target] += 1
            if relation == "about":
                in_corpus.add(target)
    return degree, in_corpus


def facts(entity: dict, local: str, lengths: dict) -> dict:
    claims = entity.get("claims", {})
    sitelinks = entity.get("sitelinks", {})
    labels, descs = entity.get("labels", {}), entity.get("descriptions", {})
    wikipedias = [k for k in sitelinks if k.endswith("wiki") and k not in ("commonswiki", "specieswiki", "metawiki")]
    row = {
        "monument_code": ", ".join(
            c["mainsnak"].get("datavalue", {}).get("value", "") for c in claims.get("P1371", [])
        ),
        "statements": sum(len(v) for v in claims.values()),
        "properties": len(claims),
        "sitelinks": len(sitelinks),
        "wikipedias": len(wikipedias),
        "has_coordinates": "P625" in claims,
        "has_image": "P18" in claims,
        "has_description_en": "en" in descs,
    }
    for lang in [*LANGS, "local"]:
        code = local if lang == "local" else lang
        if not code:
            row[f"label_{lang}"] = row[f"article_{lang}"] = ""
            row[f"article_{lang}_bytes"] = ""
            continue
        row[f"label_{lang}"] = code in labels
        title = sitelinks.get(f"{code}wiki", {}).get("title")
        row[f"article_{lang}"] = bool(title)
        row[f"article_{lang}_bytes"] = lengths.get(code, {}).get(title, "") if title else ""
    return row


def frame_comparison(wm: Wikimedia) -> list[dict]:
    asi = Counter(r["state"] for r in read_csv(LISTS_DIR / "asi_cpm.csv"))
    rows = wm.sparql("p1371_all", "SELECT ?item ?id WHERE { ?item wdt:P1371 ?id . }")
    items, base_codes = defaultdict(set), defaultdict(set)
    for r in rows:
        m = re.match(r"([NS])-([A-Z]{2})-([A-Za-z]*\d+)", r["id"])
        if not m:
            continue
        key = (m.group(1), CODE_STATE.get(m.group(2), m.group(2)))
        items[key].add(r["item"])
        # "N-UP-A45-av" is one part of the Fatehpur Sikri entry "N-UP-A45"; the base code counts the entry once.
        base_codes[key].add(m.group(0))
    out = []
    for state in sorted(set(asi) | {s for _, s in items}):
        out.append(
            {
                "state": state,
                "asi_listed": asi.get(state, 0),
                "asi_codes_on_wikidata": len(base_codes[("N", state)]),
                "asi_items_on_wikidata": len(items[("N", state)]),
                "state_codes_on_wikidata": len(base_codes[("S", state)]),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", type=Path, default=SHEET, help="the matching sheet (default: the author's)")
    parser.add_argument("--out", type=Path, default=OUT, help="output path without suffix")
    args = parser.parse_args()
    out_path = args.out
    sample = {r["sample_id"]: r for r in read_csv(SAMPLE)}
    sheet = read_csv(args.sheet)
    bad = [
        r["sample_id"]
        for r in sheet
        if r["match"].strip() and not (QID.match(r["match"].strip()) or r["match"].strip().lower() == "none")
    ]
    if bad:
        raise SystemExit(f"`match` must be a QID or none; fix these rows first: {', '.join(bad)}")

    wm = Wikimedia(RAW, pause=1.0)
    matched = sorted({r["match"].strip() for r in sheet if QID.match(r["match"].strip())})
    ents = entities(wm, matched)
    titles = defaultdict(set)
    for r in sheet:
        q = r["match"].strip()
        local = sample[r["sample_id"]]["local_lang"]
        for code in {*LANGS, local} - {""}:
            title = ents.get(q, {}).get("sitelinks", {}).get(f"{code}wiki", {}).get("title")
            if title:
                titles[code].add(title)
    lengths = {code: article_lengths(wm, code, sorted(t)) for code, t in titles.items()}
    degree, in_corpus = graph_facts()

    rows = []
    for r in sheet:
        s = sample[r["sample_id"]]
        match = r["match"].strip()
        status = "pending" if not match else ("none" if match.lower() == "none" else "matched")
        row = {
            "sample_id": r["sample_id"],
            "stratum": s["stratum"],
            "state": s["state"],
            "local_lang": s["local_lang"],
            "inclusion_prob": s["inclusion_prob"],
            "recheck": s["recheck"],
            "status": status,
            "qid": match if status == "matched" else "",
        }
        if status == "matched":
            row |= facts(ents.get(match, {}), s["local_lang"], lengths)
            row |= {"in_corpus": match in in_corpus, "graph_degree": degree.get(match, 0)}
        rows.append(row)

    columns = list(dict.fromkeys(k for row in rows for k in row))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    measures = [
        ("item on Wikidata", lambda r: r["status"] == "matched"),
        ("monument code (P1371)", lambda r: bool(r.get("monument_code"))),
        ("English description", lambda r: r.get("has_description_en") is True),
        ("Hindi label", lambda r: r.get("label_hi") is True),
        ("Kannada label", lambda r: r.get("label_kn") is True),
        ("local-language label", lambda r: r.get("label_local") is True),
        ("coordinates", lambda r: r.get("has_coordinates") is True),
        ("image", lambda r: r.get("has_image") is True),
        ("English Wikipedia article", lambda r: r.get("article_en") is True),
        ("Hindi Wikipedia article", lambda r: r.get("article_hi") is True),
        ("Kannada Wikipedia article", lambda r: r.get("article_kn") is True),
        ("local-language Wikipedia article", lambda r: r.get("article_local") is True),
        ("in corpus v1", lambda r: r.get("in_corpus") is True),
    ]
    strata = {}
    for stratum in dict.fromkeys(r["stratum"] for r in rows):
        group = [r for r in rows if r["stratum"] == stratum]
        done = [r for r in group if r["status"] != "pending"]
        matched_rows = [r for r in done if r["status"] == "matched"]
        result = {"entries": len(group), "done": len(done), "measures": {}}
        for name, test in measures:
            # A local-language measure only counts entries that have a local language (UNESCO elements have no
            # state, so none); every other measure counts every entry done.
            base = [r for r in done if r["local_lang"]] if name.startswith("local-language") else done
            k = sum(1 for r in base if test(r))
            lo, hi = wilson(k, len(base))
            result["measures"][name] = {
                "k": k,
                "n": len(base),
                "share": round(k / len(base), 3) if base else None,
                "ci95": [lo, hi],
            }
        stmts = sorted(r["statements"] for r in matched_rows)
        result["median_statements_of_matched"] = stmts[len(stmts) // 2] if stmts else None
        strata[stratum] = result

    report = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "progress": dict(Counter(r["status"] for r in rows)),
        "strata": strata,
        "full_asi_list": frame_comparison(wm),
    }
    out_path.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    out_path.with_suffix(".md").write_text(markdown(report, [m for m, _ in measures]))
    print(f"progress: {report['progress']}; Wikidata calls {wm.fetched} fetched, {wm.reused} reused")


def markdown(report: dict, measures: list[str]) -> str:
    p = report["progress"]
    out = [
        "# Coverage audit: what Wikidata holds for the sampled entries",
        "",
        f"Generated by `src/coverage_audit/fill.py` on {report['generated'][:10]} at commit `{report['commit']}` from "
        f"the author's matches (decisions 0031, 0032). Matched {p.get('matched', 0)}, no item {p.get('none', 0)}, "
        f"pending {p.get('pending', 0)}. Rates use the entries done; brackets are Wilson 95% intervals.",
        "",
    ]
    names = list(report["strata"])
    out.append("| Measure | " + " | ".join(names) + " |")
    out.append("| --- | " + " | ".join("---" for _ in names) + " |")
    out.append(
        "| Entries done | "
        + " | ".join(f"{report['strata'][s]['done']} of {report['strata'][s]['entries']}" for s in names)
        + " |"
    )
    for m in measures:
        cells = []
        for s in names:
            v = report["strata"][s]["measures"][m]
            cells.append("n/a" if v["share"] is None else f"{v['share']:.0%} [{v['ci95'][0]:.0%}, {v['ci95'][1]:.0%}]")
        out.append(f"| {m} | " + " | ".join(cells) + " |")
    out.append(
        "| Median statements, matched items | "
        + " | ".join(str(report["strata"][s]["median_statements_of_matched"] or "") for s in names)
        + " |"
    )
    out += [
        "",
        "## Full ASI list against Wikidata",
        "",
        "Distinct monument codes (P1371) per state, against the ASI list's own count. A code's sub-parts "
        "(`N-UP-A45-av`) count once under the entry (`N-UP-A45`). State-list codes (`S-…`) are shown for reference.",
        "",
        "| State | ASI list | ASI codes on Wikidata | Items with an ASI code | State-list codes on Wikidata |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in report["full_asi_list"]:
        out.append(
            f"| {r['state']} | {r['asi_listed']} | {r['asi_codes_on_wikidata']} | {r['asi_items_on_wikidata']} | "
            f"{r['state_codes_on_wikidata']} |"
        )
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
