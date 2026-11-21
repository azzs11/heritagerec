"""Fixed prompts for writing a backstory and then a query from one grid cell (decision 0021).

Kept free of other project imports so the Colab notebooks can load it from a plain clone. The
prompt text is versioned with the code; every output records PROMPT_VERSION.
"""

PROMPT_VERSION = "v1"

QUERY_TYPES = {
    "simple": "a simple keyword query of two to four words",
    "entity": "a query that names one specific site, object, person, dynasty or practice",
    "concept": "a query about a theme or idea that does not name any specific site, object, person or dynasty",
    "complex": "a full natural-language question with two or more conditions",
}
LANGUAGES = {"en": "English", "hi": "Hindi, in Devanagari script", "kn": "Kannada, in Kannada script"}
STYLES = {
    "plain": "",
    "exam": "Word it the way an exam question or exam-preparation search is worded.",
    "tourist": "Word it the way a tourist would search before or during a visit.",
    "researcher": "Word it the way a researcher would search a library catalogue.",
}


def article(noun: str) -> str:
    return ("an " if noun[0].lower() in "aeiou" else "a ") + noun


def backstory_prompt(cell: dict) -> str:
    period = "a living tradition" if cell["period"] == "living tradition" else f"the period {cell['period']}"
    region = "across India" if cell["region"] == "pan-India" else f"in {cell['region']}"
    return (
        "Someone is about to search a digital library of documents about Indian heritage: Wikipedia articles,"
        " museum object records and old books.\n\n"
        f"Who they are: {article(cell['role'])}.\n"
        f"Why they are searching: to {cell['purpose']}.\n"
        f"Topic area: {cell['area']}, {region}, {period}.\n\n"
        "In two or three sentences of English, describe this person and exactly what they want to find and why."
        " Be concrete about their need. Write only the description."
    )


def query_prompt(cell: dict, backstory: str) -> str:
    style = STYLES[cell["style"]]
    return (
        f"{backstory.strip()}\n\n"
        f"Write the one search query this person would type into the library's search box. It must be"
        f" {QUERY_TYPES[cell['query_type']]}, written in {LANGUAGES[cell['language']]}."
        + (f" {style}" if style else "")
        + " Write only the query, with no quotation marks and no explanation."
    )
