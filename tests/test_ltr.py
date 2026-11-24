"""Tests for learning to rank (src/retrieval/ltr.py, decision 0037)."""

import math

import pytest

from src.retrieval.ltr import assemble, folds_by_query, run_features


def test_run_features_scale_within_the_query_and_give_reciprocal_ranks():
    f = run_features("bm25", [("a", 10.0), ("b", 6.0), ("c", 2.0)])
    assert f["a"] == {"norm_bm25": 1.0, "rr_bm25": 1.0}
    assert f["b"]["norm_bm25"] == pytest.approx(0.5) and f["c"]["rr_bm25"] == pytest.approx(1 / 3)
    assert run_features("x", []) == {}


def test_assembly_keeps_absence_missing_and_tags_feature_groups():
    candidates = {"q1": ["d1", "d2"]}
    runs = {"bm25": {"q1": [("d1", 5.0)]}, "ppr": {"q1": [("d2", 0.3), ("d1", 0.1)]}}
    graph = {("q1", "d1"): {"overlap": 1.0, "simrank": 0.2}}
    docs = {"d1": {"words": 99, "language": "en"}, "d2": {"words": 0, "language": "hi"}}
    columns, rows, groups = assemble(candidates, runs, graph, docs, {"q1": "en"})
    d1, d2 = rows
    assert math.isnan(d2["norm_bm25"]) and d2["rr_bm25"] == 0.0  # bm25 did not return d2
    assert d1["norm_bm25"] == 1.0 and d2["overlap"] == 0.0  # no graph row: zeros
    assert d1["language_match"] == 1.0 and d2["language_match"] == 0.0
    assert d1["log_length"] == pytest.approx(math.log(100))
    assert groups["norm_ppr"] == "graph" and groups["rr_bm25"] == "text" and groups["simrank"] == "graph"
    assert groups["language_match"] == "query" and set(columns) == set(groups)


def test_folds_split_by_query_reproducibly_and_evenly():
    qids = [f"q{i:03d}" for i in range(40)]
    folds = folds_by_query(qids)
    assert folds == folds_by_query(list(reversed(qids)))  # order of input does not matter
    sizes = [sum(1 for f in folds.values() if f == k) for k in range(5)]
    assert sizes == [8, 8, 8, 8, 8]


def lightgbm_loads() -> bool:
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError):  # OSError: the OpenMP library is missing (macOS: brew install libomp)
        return False
    return True


@pytest.mark.skipif(not lightgbm_loads(), reason="LightGBM cannot load; on macOS run brew install libomp")
def test_training_is_out_of_fold_and_learns_a_planted_signal():
    # 40 queries x 20 documents; the label is planted in one feature, the other is noise.
    import random

    from src.retrieval.ltr import train_out_of_fold

    rng = random.Random(1)
    rows, labels = [], {}
    for q in range(40):
        for d in range(20):
            signal = rng.random()
            rows.append({"qid": f"q{q}", "doc_id": f"d{d}", "signal": signal, "noise": rng.random()})
            labels[(f"q{q}", f"d{d}")] = 3 if signal > 0.85 else 0
    scores, shap = train_out_of_fold(["signal", "noise"], rows, labels, folds_by_query([r["qid"] for r in rows]))
    assert abs(shap[:, 0]).mean() > 3 * abs(shap[:, 1]).mean()  # SHAP finds the planted feature
