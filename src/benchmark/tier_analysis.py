"""Does the graph's advantage hold where Wikidata is thin? The coverage-tier analysis of decision 0031 (step 4).

Reads one evaluation's per-query values (src.benchmark.evaluate writes them) and the queries' coverage tiers and
scores, and compares a graph system with a text system on NDCG@10:

1. Per tier (rich, middle, sparse; and queries with no target entity): each system's mean with a 95% percentile
   bootstrap interval, and the mean of the per-query difference (graph minus text) with its interval.
2. Interaction: is the per-query difference smaller in the sparse tier than in the rich tier? A two-sided
   permutation test on the difference of the two tiers' mean differences (tier labels shuffled).
3. Regression: the per-query difference on the continuous coverage score (ordinary least squares, statsmodels),
   with the slope's 95% interval and p-value. Queries with no target entity have no score and are left out.

These are the secondary hypotheses of 0031: they sit outside the primary Holm family and are reported with their
intervals. Settings (resamples, seed) are those of src.benchmark.evaluate.

Usage:
    uv run python -m src.benchmark.tier_analysis --name dev_v1 --queries data/queries/dev_v1.jsonl \
        --graph ppr_dev_v1 --text bm25_dev_v1
Output (next to the evaluation, results/benchmark/<name>/):
    tiers_<graph>_vs_<text>.json and .md
"""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from src.benchmark.evaluate import PRIMARY, RESAMPLES, SEED, interval
from src.corpus.wikimedia import ROOT

RESULTS = ROOT / "results/benchmark"
TIERS = ("rich", "middle", "sparse", "no entity")


def read_per_query(path: Path, measure: str = str(PRIMARY)) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            out.setdefault(row["system"], {})[row["query_id"]] = float(row[measure])
    return out


def interaction(sparse: np.ndarray, rich: np.ndarray) -> float:
    """Two-sided permutation p-value for mean(sparse) - mean(rich), tier labels shuffled."""
    from scipy.stats import permutation_test

    res = permutation_test(
        (sparse, rich),
        lambda a, b: np.mean(a) - np.mean(b),
        permutation_type="independent",
        n_resamples=RESAMPLES,
        alternative="two-sided",
        rng=SEED,
    )
    return float(res.pvalue)


def regression(scores: np.ndarray, diffs: np.ndarray) -> dict:
    import statsmodels.api as sm

    fit = sm.OLS(diffs, sm.add_constant(scores)).fit()
    lo, hi = fit.conf_int(alpha=0.05)[1]
    return {
        "queries": int(len(scores)),
        "slope": round(float(fit.params[1]), 4),
        "slope_ci95": [round(float(lo), 4), round(float(hi), 4)],
        "p": round(float(fit.pvalues[1]), 4),
        "intercept": round(float(fit.params[0]), 4),
    }


def analyse(per_query: dict, queries: list[dict], graph: str, text: str) -> dict:
    for system in (graph, text):
        if system not in per_query:
            raise SystemExit(f"{system} is not in the evaluation; systems there: {', '.join(sorted(per_query))}")
    scored = [q for q in queries if q["qid"] in per_query[graph]]
    diff = {q["qid"]: per_query[graph][q["qid"]] - per_query[text][q["qid"]] for q in scored}
    tier_of = {q["qid"]: q.get("coverage_tier") or "no entity" for q in scored}

    def summary(ids: list[str]) -> dict:
        if not ids:
            return {"queries": 0}
        out = {"queries": len(ids)}
        for label, values in (
            (graph, np.array([per_query[graph][i] for i in ids])),
            (text, np.array([per_query[text][i] for i in ids])),
            ("difference", np.array([diff[i] for i in ids])),
        ):
            lo, hi = interval(values)
            out[label] = {"mean": round(float(values.mean()), 4), "ci95": [round(lo, 4), round(hi, 4)]}
        return out

    by_tier = {t: summary([i for i in diff if tier_of[i] == t]) for t in TIERS}
    sparse = np.array([diff[i] for i in diff if tier_of[i] == "sparse"])
    rich = np.array([diff[i] for i in diff if tier_of[i] == "rich"])
    test = None
    if len(sparse) >= 2 and len(rich) >= 2:
        test = {
            "sparse_minus_rich": round(float(sparse.mean() - rich.mean()), 4),
            "p": round(interaction(sparse, rich), 4),
        }
    with_score = [q for q in scored if q.get("coverage_score") is not None]
    reg = None
    if len(with_score) >= 3:
        reg = regression(
            np.array([q["coverage_score"] for q in with_score]), np.array([diff[q["qid"]] for q in with_score])
        )
    return {
        "measure": str(PRIMARY),
        "graph": graph,
        "text": text,
        "by_tier": by_tier,
        "interaction_sparse_vs_rich": test,
        "regression_on_coverage_score": reg,
        "settings": {"bootstrap_resamples": RESAMPLES, "seed": SEED, "family": "secondary (decision 0031)"},
    }


def markdown(r: dict, name: str) -> str:
    g, t = r["graph"], r["text"]
    lines = [
        f"# Coverage tiers: {g} against {t}",
        "",
        f"Generated by `src/benchmark/tier_analysis.py` on {datetime.now(UTC).date().isoformat()} from "
        f"`results/benchmark/{name}/per_query.tsv` (decision 0031). {r['measure']}; brackets are 95% bootstrap "
        "intervals. Secondary hypotheses, outside the primary Holm family.",
        "",
        f"| Tier | Queries | {g} | {t} | Difference |",
        "| --- | --- | --- | --- | --- |",
    ]
    for tier, s in r["by_tier"].items():
        if not s["queries"]:
            lines.append(f"| {tier} | 0 | | | |")
            continue
        cells = [f"{s[k]['mean']} [{s[k]['ci95'][0]}, {s[k]['ci95'][1]}]" for k in (g, t, "difference")]
        lines.append(f"| {tier} | {s['queries']} | " + " | ".join(cells) + " |")
    test = r["interaction_sparse_vs_rich"]
    lines += ["", "Interaction (sparse minus rich, in the per-query difference): "]
    lines[-1] += (
        f"{test['sparse_minus_rich']}, permutation p = {test['p']}."
        if test
        else "not computed (fewer than two queries in a tier)."
    )
    reg = r["regression_on_coverage_score"]
    lines += [""]
    lines.append(
        f"Regression of the difference on the coverage score ({reg['queries']} queries): slope {reg['slope']} "
        f"[{reg['slope_ci95'][0]}, {reg['slope_ci95'][1]}], p = {reg['p']}."
        if reg
        else "Regression: not computed (fewer than three queries with a target entity)."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True, help="the evaluation's name (results/benchmark/<name>/)")
    p.add_argument("--queries", type=Path, required=True, help="JSONL with qid, coverage_tier, coverage_score")
    p.add_argument("--graph", required=True)
    p.add_argument("--text", required=True)
    a = p.parse_args()
    folder = RESULTS / a.name
    per_query = read_per_query(folder / "per_query.tsv")
    queries = [json.loads(line) for line in a.queries.open(encoding="utf-8")]
    report = analyse(per_query, queries, a.graph, a.text)
    stem = folder / f"tiers_{a.graph}_vs_{a.text}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    stem.with_suffix(".md").write_text(markdown(report, a.name))
    print(f"wrote {stem.with_suffix('.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
