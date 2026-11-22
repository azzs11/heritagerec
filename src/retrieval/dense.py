"""Dense baselines over the shared passages: two MiniLMs, multilingual-e5-large and BGE-M3 (decisions 0008, 0024).

Encoding runs on a GPU notebook (`notebooks/dense_baselines.ipynb`, Kaggle 2 x T4); the laptop only reads the
result files. Every model is loaded at a pinned revision, in fp16, at the input length it was trained on, with
the prefixes its model card asks for. Vectors are normalised and searched exactly (FAISS flat inner product)
over all passages in all languages, because cross-lingual matching is what RQ3 asks of these models. A document
scores as its best passage (MaxP), as in the BM25 runs.

BGE-M3 runs with all three of its outputs (the author's choice in 0024): its dense vectors find the top 3,000
passages, which are then scored 0.4 x dense + 0.2 x sparse + 0.4 x multi-vector, the weights on its model card.
The sparse and multi-vector outputs are computed for those candidates only, at query time; multi-vector output
for every passage would not fit on the notebook's disk. `--bge-dense-row` also writes the dense-only ranking.

Usage (inside the notebook):
    python -m src.retrieval.dense encode --model e5_large --passages <passages_v1.jsonl.gz> --emb <dir>
    python -m src.retrieval.dense search --model e5_large --passages <passages_v1.jsonl.gz> --emb <dir> \
        --queries data/queries/dev_v1.tsv

Queries are a TSV file: query id, language (en, hi or kn), query text (the same file the BM25 runs read).

Output:
    <emb>/<model>/chunk_NNNNN.npy and .json    fp16 passage vectors in passage-file order (notebook side only)
    <emb>/<model>/report.json                  copy of the report below, read by the search step
    results/retrieval/dense_<model>_v1.json    revision, settings, truncation counts, chunk checksums, timings
    results/retrieval/runs/<run>.trec          TREC runs, top 100 documents per query
"""

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from src.corpus.wikimedia import ROOT
from src.retrieval.bm25 import PASSAGE_DEPTH, RUNS, max_passage

PASSAGES = ROOT / "data/passages/passages_v1.jsonl.gz"
MANIFEST = ROOT / "data/passages/manifest_v1.json"
RESULTS = ROOT / "results/retrieval"
CHUNK = 10_000  # passages per saved file; a stopped session resumes at the first missing chunk
RESCORE_BATCH = 500  # BGE-M3 candidates encoded at a time, to keep multi-vector output small in memory
BGE_WEIGHTS = {"dense": 0.4, "sparse": 0.2, "colbert": 0.4}  # BGE-M3 model card


@dataclass(frozen=True)
class Model:
    repo: str
    revision: str  # Hugging Face commit, read from the model page on 22 Nov 2026
    max_length: int  # tokens, including special tokens and the prefix
    query_prefix: str = ""
    passage_prefix: str = ""
    batch_size: int = 64
    library: str = "sentence-transformers"


# Both MiniLMs were trained on 128-token inputs (all-MiniLM-L6-v2 would cut at 256 by default); e5 and
# BGE-M3 are run at 512 as recorded in 0024. Truncated passages are counted, not hidden.
MODELS = {
    "minilm_l6": Model(
        "sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", 128, batch_size=256
    ),
    "minilm_l12_multi": Model(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        128,
        batch_size=256,
    ),
    "e5_large": Model(
        "intfloat/multilingual-e5-large", "3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3", 512, "query: ", "passage: "
    ),
    "bge_m3": Model("BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181", 512, library="FlagEmbedding"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_passages(path: Path, manifest: Path = MANIFEST) -> str:
    """Refuse to run on any passage file other than the one in the committed manifest."""
    expected = json.load(open(manifest, encoding="utf-8"))["passages"]["sha256"]
    found = sha256(path)
    if found != expected:
        raise SystemExit(f"{path} has SHA-256 {found}, the manifest expects {expected}")
    return found


def read_passages(path: Path) -> tuple[list[str], list[str], list[str]]:
    ids, langs, texts = [], [], []
    for line in gzip.open(path, "rt", encoding="utf-8"):
        p = json.loads(line)
        ids.append(p["id"])
        langs.append(p["language"])
        texts.append(p["contents"])
    return ids, langs, texts


def chunks(n: int, size: int = CHUNK) -> list[tuple[int, int]]:
    return [(a, min(a + size, n)) for a in range(0, n, size)]


def truncated(lengths: list[int], langs: list[str], max_length: int) -> dict[str, int]:
    """Passages longer than the model's input length, by language (every language listed, zeros included)."""
    out = dict.fromkeys(sorted(set(langs)), 0)
    for n, lang in zip(lengths, langs, strict=True):
        if n > max_length:
            out[lang] += 1
    return out


def combine(dense: float, sparse: float, colbert: float) -> float:
    return BGE_WEIGHTS["dense"] * dense + BGE_WEIGHTS["sparse"] * sparse + BGE_WEIGHTS["colbert"] * colbert


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load(name: str, device: str):
    """Download the pinned revision, then load it from disk; BGEM3FlagModel takes no revision argument."""
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer

    spec = MODELS[name]
    path = snapshot_download(spec.repo, revision=spec.revision)
    tokenizer = AutoTokenizer.from_pretrained(path)
    if spec.library == "FlagEmbedding":
        from FlagEmbedding import BGEM3FlagModel

        model = BGEM3FlagModel(
            path,
            use_fp16=True,
            devices=[device],
            query_max_length=spec.max_length,
            passage_max_length=spec.max_length,
        )
    else:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(path, device=device)
        model.max_seq_length = spec.max_length
        model.half()
    return model, tokenizer


def embed(name: str, model, texts: list[str]) -> np.ndarray:
    """Normalised dense vectors; texts already carry their prefix."""
    spec = MODELS[name]
    if spec.library == "FlagEmbedding":
        out = model.encode(texts, batch_size=spec.batch_size, max_length=spec.max_length, return_dense=True)
        return np.asarray(out["dense_vecs"], dtype=np.float32)
    return model.encode(
        texts, batch_size=spec.batch_size, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    ).astype(np.float32)


def versions() -> dict:
    import importlib.metadata as md

    out = {}
    for pkg in ("torch", "transformers", "sentence-transformers", "FlagEmbedding", "faiss-cpu"):
        try:
            out[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            out[pkg] = None
    return out


def encode(name: str, passages: Path, emb: Path, device: str) -> None:
    import torch

    spec = MODELS[name]
    passages_sha = check_passages(passages)
    ids, langs, texts = read_passages(passages)
    model, tokenizer = load(name, device)
    out = emb / name
    out.mkdir(parents=True, exist_ok=True)

    metas = []
    for k, (a, b) in enumerate(chunks(len(ids))):
        npy, meta = out / f"chunk_{k:05d}.npy", out / f"chunk_{k:05d}.json"
        if meta.exists():  # written last, so it only exists for a finished chunk
            metas.append(json.loads(meta.read_text(encoding="utf-8")))
            continue
        batch = [spec.passage_prefix + t for t in texts[a:b]]
        start = time.time()
        vecs = embed(name, model, batch).astype(np.float16)
        seconds = round(time.time() - start, 1)
        lengths = [len(x) for x in tokenizer(batch, add_special_tokens=True)["input_ids"]]
        tmp = npy.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            np.save(f, vecs)
        tmp.rename(npy)
        m = {
            "file": npy.name,
            "start": a,
            "end": b,
            "dim": int(vecs.shape[1]),
            "seconds": seconds,
            "truncated": truncated(lengths, langs[a:b], spec.max_length),
            "sha256": sha256(npy),
        }
        meta.write_text(json.dumps(m) + "\n", encoding="utf-8")
        metas.append(m)
        print(f"{name}: chunk {k} ({a}-{b}) in {seconds} s", flush=True)

    by_lang = Counter(langs)
    cut = Counter()
    for m in metas:
        cut.update(m["truncated"])
    report = {
        "model": name,
        **asdict(spec),
        "dtype": "float16",
        "dim": metas[0]["dim"],
        "built": datetime.now(UTC).date().isoformat(),
        "commit": git_commit(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "versions": versions(),
        "passages_sha256": passages_sha,
        "passages": len(ids),
        "passages_by_language": dict(sorted(by_lang.items())),
        "truncated_by_language": {lang: cut.get(lang, 0) for lang in sorted(by_lang)},
        "truncated_share_by_language": {lang: round(cut.get(lang, 0) / by_lang[lang], 4) for lang in sorted(by_lang)},
        "encode_seconds": round(sum(m["seconds"] for m in metas), 1),
        "chunks": [{"file": m["file"], "start": m["start"], "end": m["end"], "sha256": m["sha256"]} for m in metas],
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (out / "report.json").write_text(text, encoding="utf-8")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"dense_{name}_v1.json").write_text(text, encoding="utf-8")
    print(text)


def load_vectors(name: str, emb: Path, passages_sha: str) -> np.ndarray:
    spec = MODELS[name]
    report = json.loads((emb / name / "report.json").read_text(encoding="utf-8"))
    if report["revision"] != spec.revision or report["passages_sha256"] != passages_sha:
        raise SystemExit(f"{emb / name} was encoded with another model revision or passage file")
    parts = []
    for c in report["chunks"]:
        path = emb / name / c["file"]
        if sha256(path) != c["sha256"]:
            raise SystemExit(f"{path} does not match its checksum in report.json")
        parts.append(np.load(path))
    return np.concatenate(parts).astype(np.float32)


def write_run(path: Path, name: str, ranked: dict[str, list[tuple[str, float]]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for qid, docs in ranked.items():
            for rank, (doc, score) in enumerate(docs, 1):
                f.write(f"{qid} Q0 {doc} {rank} {score:.6f} {name}\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(ranked)} queries)")


def bge_rescore(model, text: str, cand: list[int], dense: list[float], texts: list[str]) -> list[tuple[int, float]]:
    spec = MODELS["bge_m3"]
    q = model.encode(
        [text], max_length=spec.max_length, return_dense=False, return_sparse=True, return_colbert_vecs=True
    )
    q_sparse, q_colbert = q["lexical_weights"][0], q["colbert_vecs"][0]
    scored = []
    for a in range(0, len(cand), RESCORE_BATCH):
        part = cand[a : a + RESCORE_BATCH]
        p = model.encode(
            [texts[j] for j in part],
            batch_size=spec.batch_size,
            max_length=spec.max_length,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=True,
        )
        for i, j in enumerate(part):
            sparse = float(model.compute_lexical_matching_score(q_sparse, p["lexical_weights"][i]))
            colbert = float(model.colbert_score(q_colbert, p["colbert_vecs"][i]))
            scored.append((j, combine(dense[a + i], sparse, colbert)))
    # Stable sort: equal scores keep their dense order.
    return sorted(scored, key=lambda x: -x[1])


def search(name: str, passages: Path, emb: Path, queries: Path, device: str, bge_dense_row: bool) -> None:
    import faiss

    spec = MODELS[name]
    passages_sha = check_passages(passages)
    ids, _, texts = read_passages(passages)
    vectors = load_vectors(name, emb, passages_sha)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    del vectors

    # The language column is not used: a dense model searches every language.
    rows = list(csv.reader(open(queries, encoding="utf-8"), delimiter="\t"))
    if not rows:
        raise SystemExit(f"{queries} has no queries")
    model, _ = load(name, device)
    q = embed(name, model, [spec.query_prefix + text for _, _, text in rows])
    scores, idx = index.search(q, PASSAGE_DEPTH)

    stem = queries.stem
    runs: dict[str, dict] = {}
    dense_name = f"{'bge_m3_dense' if name == 'bge_m3' else name}_{stem}"
    if name != "bge_m3" or bge_dense_row:
        runs[dense_name] = {
            qid: max_passage([(ids[j], float(s)) for j, s in zip(idx[i], scores[i])])
            for i, (qid, _, _) in enumerate(rows)
        }
    if name == "bge_m3":
        all_name = f"bge_m3_all_{stem}"
        runs[all_name] = {}
        for i, (qid, _, text) in enumerate(rows):
            scored = bge_rescore(model, text, [int(j) for j in idx[i]], [float(s) for s in scores[i]], texts)
            runs[all_name][qid] = max_passage([(ids[j], s) for j, s in scored])
            print(f"bge_m3: rescored query {qid}", flush=True)

    RUNS.mkdir(parents=True, exist_ok=True)
    for run, ranked in runs.items():
        write_run(RUNS / f"{run}.trec", run, ranked)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["encode", "search"])
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--passages", type=Path, default=PASSAGES)
    parser.add_argument("--emb", type=Path, required=True, help="folder holding one subfolder of vectors per model")
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--bge-dense-row", action="store_true", help="also write BGE-M3's dense-only ranking")
    args = parser.parse_args()
    if args.command == "encode":
        encode(args.model, args.passages, args.emb, args.device)
    else:
        if not args.queries:
            raise SystemExit("search needs --queries")
        search(args.model, args.passages, args.emb, args.queries, args.device, args.bge_dense_row)


if __name__ == "__main__":
    main()
