# 0023: Keyword baselines (BM25 and BM25+RM3): tool, languages and passages

- Status: accepted (author, 2026-11-21)
- Date: 2026-11-21

## Context

Decision 0008 makes BM25 and BM25 with RM3 query expansion the keyword baselines. Three choices were open: the
tool, how Hindi and Kannada text is tokenised, and how long documents are handled. Corpus v1 has 14,485
documents (12,050 English, 1,541 Hindi, 894 Kannada). 86 of them are whole books of more than 20,000 words
(`docs/data_card.md`), and neural models read only about 512 tokens at a time.

## Options considered

Tool:

| Option | For | Against |
| --- | --- | --- |
| A. Pyserini (Anserini, Lucene) | The standard toolkit in IR papers; BM25 and RM3 built in; published reproducible baselines, including MIRACL | Needs Java 21 on the machine |
| B. PyTerrier | Also standard; RM3 available | Needs Java; weaker built-in Hindi handling |
| C. bm25s | Pure Python, no Java | No RM3, which would then be hand-written |

Tokenisation:

| Option | For | Against |
| --- | --- | --- |
| A. Each text analysed by its own language's rules: English with Porter stemming, Hindi with Lucene's Hindi analyser, Kannada with plain word splitting unless Anserini has a Kannada analyser | The setup of multilingual benchmarks such as MIRACL | Kannada gets no stemming |
| B. One multilingual subword tokenizer for all | One setup | Weaker for English keyword search |

Long documents:

| Option | For | Against |
| --- | --- | --- |
| A. Every document split into passages; a document scores as its best passage (MaxP) | Keyword and neural systems see the same units, so the comparison is fair | More units to index |
| B. Only long documents split | Fewer passages | Systems see documents differently |
| C. No splitting | Simplest for BM25 | Neural models would read only the start of each book |

## Decision

Tool A, tokenisation A, passages A.

- **Passages:** 150 words with a 75-word stride, as in BERT-MaxP (Dai and Callan, SIGIR 2019). The title is
  put at the start of every passage. 150 rather than 250 words, because Hindi and Kannada text produces many
  more model tokens per word, and 250 words would overflow 512 tokens. A document of 150 words or fewer is a
  single passage. At these settings corpus v1 gives about 283,000 passages (counted from the snapshot on
  21 Nov 2026; the index build reports the exact number).
- **The same passage file** (`data/passages/passages_v1.jsonl.gz`, built by a script, byte-identical on rebuild)
  is used by every retrieval system. Document scores are the best passage score.
- **Indexes:** one Lucene index per language, each with that language's analyser. A query is analysed with
  its own language's rules. A keyword query cannot match text in another script, so a query searches the index
  of its own language. The English index also serves romanised words that appear in Hindi or Kannada queries.
  The cross-lingual case is left to the dense models and the controls, which is what RQ3 compares.
- **Parameters:** Anserini defaults (BM25 k1 = 0.9, b = 0.4; RM3 with 10 feedback terms, 10 feedback
  documents and original-query weight 0.5) as the reported baseline. Any tuning is done on the 40 dev queries
  only, and the untuned run is reported beside it.
- **Kannada analyser:** checked in the Anserini source once it is installed; the result is recorded here.

## Consequences

- Java 21 (Eclipse Temurin JDK 21, from adoptium.net) is installed on the laptop, and `pyserini` is added to
  `pyproject.toml`.
- Indexes are built locally and are not committed. The passage file's SHA-256 goes into a manifest.
- The data card states the passage settings and the passage count by language and source.
