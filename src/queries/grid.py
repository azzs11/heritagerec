"""The grid of information needs that benchmark queries are generated from (decision 0021).

Each cell describes a searcher (role and purpose), a heritage area, a region and a period, plus the
query type, language and style wanted. Regions and periods are zones and date ranges, not names, so
no entity from the corpus enters a query through the grid. The generator sees one cell at a time and
nothing else: no entity lists, corpus, gazetteer or system output.

Usage (writes the 30 cells of the generator trial):
    uv run python -m src.queries.grid

Output:
    data/queries/generator_trial_cells_v1.jsonl
"""

import json
import random

from src.corpus.wikimedia import ROOT
from src.queries.prompts import LANGUAGES, QUERY_TYPES

TRIAL_CELLS = ROOT / "data/queries/generator_trial_cells_v1.jsonl"
TRIAL_SEED = 20261121
TRIAL_PER_LANGUAGE = 10

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


def main() -> None:
    rng = random.Random(TRIAL_SEED)
    cells = sample_cells(rng, trial_slots())
    TRIAL_CELLS.parent.mkdir(parents=True, exist_ok=True)
    with open(TRIAL_CELLS, "w", encoding="utf-8") as f:
        for i, cell in enumerate(cells, 1):
            f.write(json.dumps({"cell_id": f"trial-{i:02d}", **cell}, ensure_ascii=False) + "\n")
    print(f"wrote {TRIAL_CELLS.relative_to(ROOT)} ({len(cells)} cells)")


if __name__ == "__main__":
    main()
