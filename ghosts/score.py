import re

GRAMMAR = re.compile(r"^[AB],[AB],[AB]$")


def parse_three_letters(text: str) -> tuple[str, str, str] | None:
    stripped = text.strip()
    if not GRAMMAR.match(stripped):
        return None
    return tuple(stripped.split(","))


def semantic_answers(text: str, option_mappings: dict) -> dict | None:
    letters = parse_three_letters(text)
    if letters is None:
        return None
    return {
        "q1": option_mappings["q1"][letters[0]],
        "q2": option_mappings["q2"][letters[1]],
        "q3": option_mappings["q3"][letters[2]],
    }


def any_flip(first: str | None, second: str | None) -> bool | None:
    if first is None or second is None:
        return None
    return first != second


def canary_leaks(text: str, canary: str) -> bool:
    return canary in text
