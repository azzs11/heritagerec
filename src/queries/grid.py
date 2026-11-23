"""The grid of information needs that benchmark queries are generated from (decision 0021).

Each cell describes a searcher (role and purpose), a heritage area, a region and a period, plus the
query type, language and style wanted. Regions and periods are zones and date ranges, not names, so
no entity from the corpus enters a query through the grid. The generator sees one cell at a time and
nothing else: no entity lists, corpus, gazetteer or system output.

Usage:
    uv run python -m src.queries.grid trial        the 30 cells of the generator trial
    uv run python -m src.queries.grid benchmark    the 200 benchmark slots, each with two reserve cells

Outputs:
    data/queries/generator_trial_cells_v1.jsonl
    data/queries/benchmark_cells_v1.jsonl     600 cells: rank 0 is the slot's cell, ranks 1 and 2 its reserves
"""

import argparse
import json
import random

from src.corpus.wikimedia import ROOT
from src.queries.prompts import LANGUAGES, QUERY_TYPES

TRIAL_CELLS = ROOT / "data/queries/generator_trial_cells_v1.jsonl"
TRIAL_SEED = 20261121
TRIAL_PER_LANGUAGE = 10
BENCHMARK_CELLS = ROOT / "data/queries/benchmark_cells_v1.jsonl"
BENCHMARK_SEED = 20261123
# Decision 0021: 40 English queries per type, 5 Hindi and 5 Kannada; 40 real-style queries, spread over the
# types and over the languages in proportion (32 English, 4 Hindi, 4 Kannada).
PER_TYPE = {"en": 40, "hi": 5, "kn": 5}
REAL_STYLE_PER_TYPE = {"en": 8, "hi": 1, "kn": 1}
RESERVES = 2

ROLES = {
    "school student": ["do homework", "prepare a class project"],
    "civil-services or state exam aspirant": [
        "revise art-and-culture facts",
        "check a fact for an exam answer",
    ],
    "undergraduate student of history, architecture or fine arts": [
        "write an essay",
        "compare two traditions or styles",
    ],
    "researcher (historian, art historian or epigraphist)": [
        "find primary sources",
        "trace how something changed over time",
    ],
    "domestic tourist or pilgrim": ["plan a visit", "learn what to look for at a place"],
    "foreign visitor": ["understand a place or practice before a trip"],
    "museum curator or collector": [
        "identify, date or place an object",
        "find comparable objects",
    ],
    "teacher": ["prepare a lesson"],
    "performer or craftsperson": ["learn the origins and lineage of their form"],
    "journalist or writer": ["gather background for a feature"],
    "local heritage enthusiast": ["learn the history of their home area"],
}
AREAS = [
    "temples and religious architecture",
    "forts, palaces and civic architecture",
    "sculpture and bronzes",
    "painting and manuscripts",
    "inscriptions and coins",
    "textiles, crafts and decorative arts",
    "music",
    "dance and theatre",
    "festivals and rituals",
    "rulers, dynasties and patrons",
]
REGIONS = ["north India", "south India", "east India", "west India", "central India", "north-east India", "pan-India"]
PERIODS = ["before 600 CE", "600 to 1200 CE", "1200 to 1550 CE", "1550 to 1800 CE", "1800 to 1947", "living tradition"]
# A real-style query only makes sense from a searcher who would word it that way.
STYLE_ROLES = {
    "exam": ["civil-services or state exam aspirant", "school student", "teacher"],
    "tourist": ["domestic tourist or pilgrim", "foreign visitor"],
    "researcher": ["researcher (historian, art historian or epigraphist)", "museum curator or collector"],
}


def cycle(rng: random.Random, items: list, n: int) -> list:
    """n items drawn so that each appears about equally often: shuffled passes over the list."""
    out = []
    while len(out) < n:
        batch = list(items)
        rng.shuffle(batch)
        out += batch
    return out[:n]


def sample_cells(rng: random.Random, slots: list[dict]) -> list[dict]:
    """Fill each slot (type, language, style) with a role, purpose, area, region and period."""
    n = len(slots)
    roles = cycle(rng, list(ROLES), n)
    areas, regions, periods = cycle(rng, AREAS, n), cycle(rng, REGIONS, n), cycle(rng, PERIODS, n)
    cells = []
    for i, slot in enumerate(slots):
        if slot["style"] in STYLE_ROLES:
            roles[i] = rng.choice(STYLE_ROLES[slot["style"]])
        cells.append(
            {
                **slot,
                "role": roles[i],
                "purpose": rng.choice(ROLES[roles[i]]),
                "area": areas[i],
                "region": regions[i],
                "period": periods[i],
            }
        )
    return cells


def trial_slots() -> list[dict]:
    """10 cells per language across the four types; one real-style cell per language for each style."""
    slots = []
    types = list(QUERY_TYPES)
    # Each language starts the type rotation at a different type, so the 30 cells split 8/8/7/7, not 9/9/6/6.
    for offset, lang in zip((0, 2, 1), LANGUAGES):
        styles = ["exam", "tourist", "researcher"] + ["plain"] * (TRIAL_PER_LANGUAGE - 3)
        for i in range(TRIAL_PER_LANGUAGE):
            slots.append({"query_type": types[(i + offset) % len(types)], "language": lang, "style": styles[i]})
    return slots


def benchmark_slots(rng: random.Random) -> list[dict]:
    """The 200 slots of decision 0021: language x type quotas, with the real-style slots marked."""
    slots = []
    for lang, n in PER_TYPE.items():
        for qtype in QUERY_TYPES:
            real = REAL_STYLE_PER_TYPE[lang]
            slots += [{"query_type": qtype, "language": lang, "style": "real"}] * real
            slots += [{"query_type": qtype, "language": lang, "style": "plain"}] * (n - real)
    slots = [dict(s) for s in slots]
    # The three real styles are dealt in shuffled passes, so each is used about equally (13, 13, 14).
    real = [s for s in slots if s["style"] == "real"]
    for slot, style in zip(real, cycle(rng, list(STYLE_ROLES), len(real)), strict=True):
        slot["style"] = style
    return slots


def benchmark_cells() -> list[dict]:
    """Each slot gets its cell (rank 0) and two reserves; every rank is its own balanced pass over the grid."""
    rng = random.Random(BENCHMARK_SEED)
    slots = benchmark_slots(rng)
    cells = []
    for rank in range(RESERVES + 1):
        # A reserve is used only when the author rejects the slot's backstory or query at curation.
        for i, cell in enumerate(sample_cells(random.Random(f"{BENCHMARK_SEED}:{rank}"), slots), 1):
            cells.append({"cell_id": f"q{i:03d}-{rank}", "slot": f"q{i:03d}", "rank": rank, **cell})
    return cells


def write(path, cells) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for cell in cells:
            f.write(json.dumps(cell, ensure_ascii=False) + "\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(cells)} cells)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("which", choices=["trial", "benchmark"])
    args = parser.parse_args()
    if args.which == "trial":
        cells = sample_cells(random.Random(TRIAL_SEED), trial_slots())
        write(TRIAL_CELLS, [{"cell_id": f"trial-{i:02d}", **c} for i, c in enumerate(cells, 1)])
    else:
        write(BENCHMARK_CELLS, benchmark_cells())


if __name__ == "__main__":
    main()
