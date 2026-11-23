# notebooks

Colab notebooks for the steps that need a GPU (models, embeddings, reranking, translation, LLM generation and
judging). They clone this repository, import the fixed prompts and settings from `src/`, and write result files
that are copied back into `results/`. Nothing in a notebook is a source of numbers by itself: every number comes
from a result file that a script in `src/` reads.

| Notebook | What it does | Writes | Decision |
| --- | --- | --- | --- |
| `query_generation.ipynb` | Sarvam-M writes the 200 benchmark queries (and reserves for rejected slots) at the revision the trial chose | `results/queries/generation_v1/outputs.jsonl` | 0021 |
| `query_generator_trial.ipynb` | Three open-weight models write a backstory and a query for the same 30 grid cells, for the author's blind rating | `results/queries/generator_trial_v1/outputs.jsonl` | 0021 |
| `dense_baselines.ipynb` | Encodes the shared passages with the two MiniLMs, multilingual-e5-large and BGE-M3 on Kaggle (2 x T4), then writes TREC runs once the dev queries exist | `results/retrieval/dense_<model>_v1.json`, `results/retrieval/runs/*.trec` | 0024 |
