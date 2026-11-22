# 0024: Dense baselines (MiniLM, BGE-M3, multilingual-e5): models, passages and search

- Status: accepted (author, 2026-11-22)
- Date: 2026-11-22

## Context

Decision 0008 makes MiniLM, BGE-M3 and multilingual-e5 the dense baselines. Five choices were open: which MiniLM,
which e5, which BGE-M3 output, how passages are fed in, and how and where the search runs. Decision 0023 already
fixes the units: every system reads the same passage file (`data/passages/passages_v1.jsonl.gz`, 282,274 passages
of 150 words, stride 75, title first) and a document scores as its best passage (MaxP). The laptop has 16 GB of
RAM and no GPU, so encoding runs on a free GPU notebook and only run files come back.

Model facts below were read from the Hugging Face model pages on 22 Nov 2026.

| Model | Licence | Size | Trained input length | Kannada in training languages |
| --- | --- | --- | --- | --- |
| all-MiniLM-L6-v2 (the conference version's model) | Apache-2.0 | 22M | 128 tokens (cuts at 256 by default) | No (English only) |
| paraphrase-multilingual-MiniLM-L12-v2 | Apache-2.0 | 118M | 128 tokens | No (Hindi yes; 50 languages) |
| BAAI/bge-m3 | MIT | 568M (2.27 GB of fp32 weights) | 8,192 tokens | Not listed per language; XLM-R base covers Kannada |
| intfloat/multilingual-e5-base | MIT | 278M | 512 tokens | Yes |
| intfloat/multilingual-e5-large | MIT | 560M | 512 tokens | Yes |
| intfloat/multilingual-e5-large-instruct | MIT | 560M | 512 tokens | Yes |

## Options considered

MiniLM:

| Option | For | Against |
| --- | --- | --- |
| A. all-MiniLM-L6-v2 | Same model as the conference version, so the old and new numbers line up | English only: Hindi and Kannada queries and documents are effectively unreadable to it |
| B. paraphrase-multilingual-MiniLM-L12-v2 | Small multilingual model; reads Hindi | Not trained on Kannada; trained on 128-token inputs, so most of a 150-word passage is cut |
| C. Both, A labelled as the conference-version row | Continuity and a fair small multilingual model | One more run (cheap: the smallest model) |

multilingual-e5:

| Option | For | Against |
| --- | --- | --- |
| A. base | Faster | Weaker; the large model is the one usually reported on MIRACL |
| B. large | The size reported in the e5 technical report (Wang et al. 2024) and in MIRACL comparisons; same size as BGE-M3, so the two compare fairly | Slower to encode |
| C. large-instruct | Usually a little stronger | Needs a task instruction written by us, one more choice to defend |

BGE-M3 output:

| Option | For | Against |
| --- | --- | --- |
| A. Dense vectors only | A clean dense baseline next to e5 and MiniLM | Leaves its sparse and multi-vector outputs unused |
| B. Dense + sparse + multi-vector (as in the BGE-M3 paper, Chen et al. 2024) | Its strongest setting | Mixes lexical matching into the "dense" row, so it no longer isolates dense retrieval; multi-vector storage is large |

Input length (passages are already 150 words):

| Option | For | Against |
| --- | --- | --- |
| A. Each model at its trained length (both MiniLMs 128, e5 512, BGE-M3 512), and the share of truncated passages reported per model and language | Each model used as designed; the cut is measured, not hidden | MiniLM sees less text |
| B. All at 512 | Same text for every model | MiniLM was never trained on inputs that long |

Search and tooling:

| Option | For | Against |
| --- | --- | --- |
| A. sentence-transformers to encode; exact inner-product search (FAISS flat index); the same MaxP code as BM25 | Exact results, no approximation error; same aggregation as the keyword runs; the BEIR setup (Thakur et al. 2021) | Embeddings must stay on the notebook side |
| B. Pyserini's dense encoders and FAISS search | One toolkit for keyword and dense | Fewer of these models are wired in; harder to pin a model revision |
| C. Approximate search (HNSW) | Faster queries | Approximation error in a baseline; not needed at 282K passages |

Where it runs:

| Option | For | Against |
| --- | --- | --- |
| A. Kaggle notebook (2 x T4) | Same platform as the judge (0022); longer sessions | Weekly GPU quota |
| B. Colab free (1 x T4) | Already used for the generator trial | Sessions can stop mid-encode, so encoding must resume from saved chunks |

## Recommendation

MiniLM C, e5 B, BGE-M3 A, input length A, search A, platform A (the notebook also works on Colab, with encoding
saved in chunks so a stopped session resumes).

- Every model is loaded at a pinned revision (commit hash recorded in the run metadata), in fp16, with the
  prefixes each model card asks for (e5: `query: ` and `passage: `; BGE-M3 and MiniLM: none). Vectors are
  normalised and scored by inner product.
- A dense model searches all passages in all languages, since cross-lingual matching is what RQ3 asks of it.
  Top 3,000 passages per query, MaxP to the top 100 documents, written as TREC runs like the BM25 runs.
- Passage embeddings stay on the notebook side (Kaggle dataset or Drive) with their SHA-256; only run files,
  the run metadata and the truncation counts come back to the repo.
- The notebook reads the committed passage manifest and refuses to run if the passage file's checksum differs.

## Decision

MiniLM C, e5 B, **BGE-M3 B**, input length A, search A, platform A. The author chose all three BGE-M3 outputs
rather than dense only; everything else follows the recommendation.

How BGE-M3 B is run:

- Encoded with FlagEmbedding (`BGEM3FlagModel`, MIT licence), which returns all three outputs.
- Dense vectors go into the same exact flat index as the other models and give the candidates: top 3,000
  passages per query.
- The candidates are then scored by the weighted sum on the model card,
  0.4 x dense + 0.2 x sparse + 0.4 x multi-vector, then MaxP to the top 100 documents.
- Multi-vector embeddings are not stored for the whole corpus: one 1,024-number vector per token for 282,274
  passages would be far larger than the notebook's disk. Sparse and multi-vector outputs are both computed for
  the candidate passages only, at query time, so only dense vectors are stored. This costs one extra encoding of
  3,000 passages per query.
- Since the combined score includes keyword-like sparse matching, the paper names this row "BGE-M3
  (dense+sparse+multi-vector)", not a pure dense row.

## Consequences

- New: `src/retrieval/dense.py` (encode, search, MaxP through the existing `max_passage`; BGE-M3 candidate scoring), a notebook in
  `notebooks/`, tests for prefixes, truncation counts and run-file format.
- Runs on the 40 dev queries wait for the queries (decision 0021). Until then, only the passage embeddings are
  built.
- The data card and `src/retrieval/README.md` gain the model revisions and truncation shares once measured.
- Library versions on the notebook: FlagEmbedding 1.4.2 fails to import with transformers 5 (checked
  22 Nov 2026), so the notebook pins transformers 4.57.6, sentence-transformers 5.7.0, FlagEmbedding 1.4.2 and
  faiss-cpu 1.15.1. These are notebook-only and not added to `pyproject.toml`, whose lock keeps transformers 5
  for the laptop. BGEM3FlagModel takes no revision argument, so every model is downloaded at its pinned commit
  first and loaded from disk.
