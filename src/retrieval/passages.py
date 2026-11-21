"""Split every corpus document into overlapping passages, shared by all retrieval systems (decision 0023).

Passages are 150 words with a 75-word stride (BERT-MaxP, Dai and Callan 2019), each starting with the
document's title. A document of 150 words or fewer is one passage. Systems score a document by its best
passage, so keyword and neural systems see exactly the same units.

Usage:
    uv run python -m src.retrieval.passages

Output:
    data/passages/passages_v1.jsonl.gz       one passage per line: id, doc_id, language, contents (not in git)
    data/passages/manifest_v1.json           settings, counts and SHA-256 of the passage file (in git)
"""

import gzip
import hashlib
import io
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime

from src.corpus.wikimedia import ROOT

SNAPSHOT = ROOT / "data/corpus_v1/records.jsonl.gz"
OUT = ROOT / "data/passages/passages_v1.jsonl.gz"
MANIFEST = ROOT / "data/passages/manifest_v1.json"
WORDS = 150
STRIDE = 75


def windows(words: list[str], size: int = WORDS, stride: int = STRIDE) -> list[list[str]]:
    """Windows start every `stride` words until one reaches the end; the last may be shorter. Nothing is dropped."""
    out, start = [], 0
    while True:
        out.append(words[start : start + size])
        if start + size >= len(words):
            return out
        start += stride


def passages(record: dict) -> list[dict]:
    title = record["title"].strip()
    return [
        {
            "id": f"{record['id']}#{i}",
            "doc_id": record["id"],
            "language": record["language"],
            "contents": f"{title}\n{' '.join(w)}" if w else title,
        }
        for i, w in enumerate(windows(record["text"].split()))
    ]


def main() -> None:
    buf = io.BytesIO()
    counts, by_source, docs = Counter(), Counter(), Counter()
    # gzip with mtime 0 and no file name, so the same snapshot gives the same bytes.
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        for line in gzip.open(SNAPSHOT, "rt", encoding="utf-8"):
            record = json.loads(line)
            ps = passages(record)
            docs[record["language"]] += 1
            counts[record["language"]] += len(ps)
            by_source[record["source"]] += len(ps)
            for p in ps:
                gz.write((json.dumps(p, ensure_ascii=False) + "\n").encode("utf-8"))
    data = buf.getvalue()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    snapshot_sha = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    manifest = {
        "built": datetime.now(UTC).date().isoformat(),
        "commit": commit,
        "snapshot_sha256": snapshot_sha,
        "settings": {"words": WORDS, "stride": STRIDE, "title_prefix": True, "split": "whitespace"},
        "passages": {
            "path": str(OUT.relative_to(ROOT)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        },
        "documents_by_language": dict(docs.most_common()),
        "passages_by_language": dict(counts.most_common()),
        "passages_by_source": dict(by_source.most_common()),
        "passages_total": sum(counts.values()),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
