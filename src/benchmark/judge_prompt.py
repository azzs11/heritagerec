"""The fixed relevance-judging prompt (specification Section 9, decision 0022).

Adapted from UMBRELA's zero-shot prompt (Upadhyay et al., 2024): castorini/umbrela, file
src/umbrela/prompts/prompt_templates/qrel_zeroshot_bing.yaml, commit 01cc3abfb11fdce82613cf4d58254bb52095c04e,
SHA-256 0acee5259241028d3edb2a4f6a142238f8616f661eda75c37197447f2df2d0e1, Apache-2.0. Two changes, both required
by the benchmark rules:

1. The scale is the specification's: 3 directly about the query, 2 clearly related, 1 loosely related, 0 not
   relevant. UMBRELA's wording is about answering a question; our queries are information needs.
2. A one-sentence rationale comes before the score line, because every judgement is saved with its rationale.
   UMBRELA asks for no reasoning.

UMBRELA's steps (intent, match M, trustworthiness T, final score O) and its "##final score:" line are kept. The
judge sees only the query, the document's title and its text, cut to TEXT_WORDS words. Kept free of other project
imports so the Kaggle notebook can load it from a plain clone; every judgement records PROMPT_VERSION and the
prompt's SHA-256.
"""

import hashlib
import re

PROMPT_VERSION = "v1"
TEXT_WORDS = 800  # the document text the judge reads: its first 800 words

TEMPLATE = """Given a search query and a document, you must provide a relevance score on an integer scale of 0 to 3 with the following meanings:
0 = the document is not relevant to the query,
1 = the document is loosely related to the query,
2 = the document is clearly related to the query,
3 = the document is directly about what the query asks for.

Important Instruction: Assign category 1 if the document is somewhat related to the topic but not completely, category 2 if the document presents something very important related to the entire topic but also has some extra information, and category 3 if the document only and entirely refers to the topic. If none of the above satisfies give it category 0. The query and the document may be in English, Hindi or Kannada, and need not be in the same language.

Query: {query}
Document title: {title}
Document text: {text}

Split this problem into steps:
Consider the underlying intent of the search.
Measure how well the content matches a likely intent of the query (M).
Measure how trustworthy the document is (T).
Consider the aspects above and the relative importance of each, and decide on a final score (O). Final score must be an integer value only.
Do not provide any code in result. Write one sentence giving the main reason for your score, then on its own line write the score in the format: ##final score: score"""

SCORE = re.compile(r"##\s*final score\s*:\s*([0-3])\b", re.I)


def cut(text: str, words: int = TEXT_WORDS) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + (" …" if len(parts) > words else "")


def judge_prompt(query: str, title: str, text: str) -> str:
    return TEMPLATE.format(query=query.strip(), title=title.strip(), text=cut(text))


def parse(output: str) -> tuple[int | None, str]:
    """The label (None if the output has no valid score line) and the rationale written before it."""
    matches = list(SCORE.finditer(output))
    if not matches:
        return None, output.strip()
    last = matches[-1]
    return int(last.group(1)), output[: last.start()].strip()


def template_sha256() -> str:
    return hashlib.sha256(TEMPLATE.encode("utf-8")).hexdigest()
