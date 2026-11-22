# 0019: Translate-then-search control: IndicTrans2 size, running it free, and checking the translations

- Status: accepted (author, 2026-11-22)
- Date: 2026-11-22

## Context

The specification (Section 4) fixes one control for RQ3: Hindi and Kannada queries translated to English with
IndicTrans2 (AI4Bharat), then searched with BM25 and the dense models. If the graph only beats text across
languages because the text systems cannot read the query, this control shows it. Decision 0008 left the model
size and how to run it free to this record. Only queries are translated, not documents: 40 of the 200 queries
(20 Hindi, 20 Kannada), 8 of them in the dev set if the split keeps the language shares.

Facts below were read from the Hugging Face model pages on 22 Nov 2026.

| Model | Licence | Size | Covers Hindi and Kannada | Note |
| --- | --- | --- | --- | --- |
| ai4bharat/indictrans2-indic-en-1B | MIT | 1.0B | Yes | Gated: accept terms on the page (approved automatically) |
| ai4bharat/indictrans2-indic-en-dist-200M | MIT | 228M | Yes | Distilled from the 1B model; same gate |
| google/madlad400-3b-mt | Apache-2.0 | 2.9B | Yes | General model for 400+ languages |
| facebook/nllb-200 (600M, 3.3B) | CC-BY-NC-4.0 | | Yes | NonCommercial: ruled out by the licence rule |
| sarvamai/sarvam-translate | GPL-3.0 | 4.3B | Yes | Fine-tuned from Gemma 3 4B, so Gemma terms apply too |

IndicTrans2 needs IndicTransToolkit (MIT, version 1.1.1) for the script and punctuation pre- and post-processing.

## Options considered

Model size:

| Option | For | Against |
| --- | --- | --- |
| A. IndicTrans2 1B (indic-en) | The model reported in the IndicTrans2 paper (Gala et al., TMLR 2023); best quality; still small enough for a free T4 | Bigger download |
| B. IndicTrans2 distilled 200M | Fast; runs on the laptop CPU | A little weaker; a weaker translation makes the control easier to beat, which reviewers would question |
| C. 1B, with MADLAD-400 3B as a second translation row | Shows the result does not depend on one translator | Second model to run and report; not in the must-ship list |

Where it runs (only about 40 short queries, so speed does not matter):

| Option | For | Against |
| --- | --- | --- |
| A. In the dense notebook on Kaggle, before the dense query encoding | Translated queries go straight into the dense search; one session | Ties translation to the dense notebook |
| B. Its own small notebook (Kaggle or Colab); output a TSV of translations committed to the repo | Translations are a fixed, reviewable file; BM25 then runs on the laptop from it; any system reuses them | One more notebook |
| C. Laptop CPU | No notebook | Against the rule that models run off the laptop |

Checking the translations:

| Option | For | Against |
| --- | --- | --- |
| A. None; report the control as is | No author time | A bad translation cannot be told apart from a bad retriever |
| B. The author reads every translated query and marks it adequate or not (meaning kept, entity names right); the share is reported; translations are never edited | The control stays a real machine-translation system, and its weak points are known | About 40 short readings |
| C. The author corrects bad translations | Cleaner control | No longer an automatic system; the control would get human help the other systems do not |

Which systems run on the translated queries:

| Option | For | Against |
| --- | --- | --- |
| A. BM25 only | Cheapest | The specification asks for BM25 and dense |
| B. BM25, BM25+RM3 and every dense model (English index for keyword search; whole corpus for dense) | Every text system gets the same help, so RQ3 compares like with like | More run files (query encoding only; passages are already encoded) |

## Recommendation

Model A, running B, checking B, systems B.

- Settings from the model card: beam search with 5 beams, maximum length 256, source tags `hin_Deva` and
  `kan_Knda`, target `eng_Latn`. The model revision (commit hash), toolkit version and date are saved with the
  translations.
- Output: `data/queries/translations_v1.tsv` (query id, source language, original text, English text), made by
  a script from the curated queries, plus the author's adequacy column in a separate file so the machine output
  stays untouched.
- Test-query translations are made at the same time as dev ones, but their search runs wait for the frozen
  analysis plan like every other test run.

## Decision

Model A, running B, checking B, systems B, as recommended.

## Consequences

- New: `src/queries/translate.py` (builds the TSV; the notebook calls it), a small notebook in `notebooks/`,
  a test that every Hindi and Kannada query has exactly one translation.
- The control's runs are named `<system>+translate` and sit beside the original runs in each results table.
- The adequacy share is reported with the control's numbers, per language.
