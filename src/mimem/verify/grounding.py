"""Rule GRD-03: numbers, names, dates and directions, checked against the source verbatim.

The premise is narrow and deliberately so. This does not ask whether a generated sentence is a
*good* summary -- that is `GRD-02` and it needs a model. It asks whether the facts it states in
checkable form appear in the text it was written from. Four kinds of fact are checkable that way:

**Numbers.** Every digit-bearing token in the generated text must appear in the source. Formats
are normalised first, because "0.0837", "0·0837" and "0,0837" are the same number and "300 %" and
"300%" are the same value. A number the source never states is either an invention or an
arithmetic step nobody asked for, and both are worth stopping.

**Years.** A four-digit year is a citation-shaped claim -- "first described in 1979" -- and a
wrong one is impossible to catch by ear.

**Names.** A capitalised word that is not sentence-initial, not a known common word, and not in
the source is a name the model supplied. Sometimes that is a real invention; often it is a
paraphrase artefact. Reported as a warning, because the false-positive rate on ordinary English
is not zero and an error nobody can act on is noise.

**Directions.** The flipped sign. If the generated text says a quantity *increases* and the
source sentences say it *decreases*, and never say it increases, the claim has been inverted.
This is the check the rule was written for, and the only one of the four that catches a failure
which reads perfectly.

What this cannot catch: a fluent sentence that draws a wrong conclusion from correct numbers.
That is what the entailment pass is for, and what the note at the top of
:mod:`mimem.verify` says about a missing check never looking like a passed one.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

#: Directional pairs. A generated claim using one side is checked against the source using the
#: other: the failure is not "this word is missing", it is "the source says the opposite".
DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("increase", "decrease"),
    ("increases", "decreases"),
    ("increased", "decreased"),
    ("increasing", "decreasing"),
    ("rise", "fall"),
    ("rises", "falls"),
    ("rose", "fell"),
    ("rising", "falling"),
    ("grow", "shrink"),
    ("grows", "shrinks"),
    ("grew", "shrank"),
    ("higher", "lower"),
    ("greater", "smaller"),
    ("more", "less"),
    ("faster", "slower"),
    ("thicker", "thinner"),
    ("longer", "shorter"),
    ("above", "below"),
    ("gains", "loses"),
    ("improves", "worsens"),
    ("accelerates", "slows"),
    ("expands", "contracts"),
)

#: Capitalised words that are not names. Short and boring on purpose: the name check is a
#: warning, so the cost of a miss is low and the cost of a long hand-maintained list is not.
_COMMON_CAPITALISED = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "so",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "there",
        "here",
        "when",
        "where",
        "while",
        "because",
        "although",
        "however",
        "therefore",
        "thus",
        "hence",
        "instead",
        "unlike",
        "each",
        "every",
        "both",
        "either",
        "neither",
        "it",
        "its",
        "it's",
        "they",
        "them",
        "their",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "his",
        "her",
        "i",
        "in",
        "on",
        "at",
        "by",
        "for",
        "from",
        "with",
        "without",
        "into",
        "onto",
        "over",
        "under",
        "across",
        "through",
        "during",
        "after",
        "before",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "can",
        "could",
        "may",
        "might",
        "must",
        "should",
        "will",
        "would",
        "shall",
        "not",
        "no",
        "yes",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "first",
        "second",
        "third",
        "figure",
        "table",
        "equation",
        "section",
        "chapter",
        "appendix",
        "panel",
        "page",
        "note",
        "picture",
        "imagine",
        "think",
        "consider",
        "suppose",
        "remember",
        "notice",
    ]
)

_NUMBER = re.compile(r"\d[\d.,·]*(?:\s*[eE][-+]?\d+)?")
_YEAR = re.compile(r"(?<!\d)(1[6-9]\d{2}|20\d{2})(?!\d)")
_WORD = re.compile(r"[A-Za-z][\w'-]*")
_SENTENCE_START = re.compile(r"(?:^|[.!?:;]\s+|\n\s*)$")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    """One checkable fact that the source does not support."""

    kind: str  # "number" | "year" | "name" | "direction"
    value: str
    message: str
    severity: Severity = Severity.ERROR

    def __str__(self) -> str:
        return f"{self.kind} {self.value!r}: {self.message}"


def _fold(text: str) -> str:
    """Normalise the ways the same number gets written."""
    folded = unicodedata.normalize("NFKD", text)
    folded = folded.replace("·", ".").replace("−", "-").replace("–", "-")
    return folded


def numbers_in(text: str) -> list[str]:
    """Every numeric token, in a canonical form: "0,0837" and "0·0837" both give "0.0837"."""
    out: list[str] = []
    for match in _NUMBER.finditer(_fold(text)):
        token = match.group(0).rstrip(".,")
        if not token:
            continue
        out.append(_canonical_number(token))
    return out


def _canonical_number(token: str) -> str:
    """Strip thousands separators and trailing zeros so that 82.10 == 82.1 == 82,1."""
    token = token.replace(" ", "")
    # A comma is a decimal point when exactly two or more digits follow and no period is present.
    if "," in token and "." not in token:
        head, _, tail = token.rpartition(",")
        token = f"{head}.{tail}" if len(tail) != 3 else f"{head}{tail}"
    token = token.replace(",", "")
    if "." in token:
        token = token.rstrip("0").rstrip(".") or "0"
    try:
        return f"{float(token):g}"
    except ValueError:
        return token


def _source_numbers(source: str) -> set[str]:
    return set(numbers_in(source))


def _names_in(text: str) -> list[str]:
    """Capitalised words that look like names rather than sentence openings."""
    out: list[str] = []
    for match in _WORD.finditer(text):
        word = match.group(0)
        if not word[0].isupper() or word.isupper():
            continue  # an acronym is not a name; SYM-02 handles those
        if word.lower() in _COMMON_CAPITALISED:
            continue
        if _SENTENCE_START.search(text[: match.start()]) or match.start() == 0:
            continue
        out.append(word)
    return out


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def check(generated: str, source: str) -> list[Finding]:
    """Every checkable claim in ``generated`` that ``source`` does not support (rule GRD-03).

    ``source`` is the concatenation of the spans the generated text was written from -- not the
    whole document. Checking against the whole document would pass a sentence that mixes up two
    unrelated results, which is exactly the kind of plausible-sounding error this is for.
    """
    findings: list[Finding] = []
    source_numbers = _source_numbers(source)
    source_words = _words(source)
    source_lower = _fold(source).lower()

    for value in dict.fromkeys(numbers_in(generated)):
        if value not in source_numbers:
            findings.append(
                Finding(
                    kind="number",
                    value=value,
                    message="does not appear in the cited source",
                )
            )

    for year in dict.fromkeys(_YEAR.findall(generated)):
        if year not in source:
            findings.append(
                Finding(kind="year", value=year, message="does not appear in the cited source")
            )

    for name in dict.fromkeys(_names_in(generated)):
        if name.lower() not in source_words:
            findings.append(
                Finding(
                    kind="name",
                    value=name,
                    message="a proper noun the cited source does not contain",
                    severity=Severity.WARNING,
                )
            )

    findings.extend(_direction_findings(generated, source_lower))
    return findings


def _direction_findings(generated: str, source_lower: str) -> list[Finding]:
    """The flipped sign: the generated text says one direction, the source says the other."""
    said = _words(generated)
    out: list[Finding] = []
    for positive, negative in DIRECTIONS:
        for used, opposite in ((positive, negative), (negative, positive)):
            if used not in said:
                continue
            if _has_word(source_lower, used):
                continue
            if _has_word(source_lower, opposite):
                out.append(
                    Finding(
                        kind="direction",
                        value=used,
                        message=f"the cited source says {opposite!r}, not {used!r}",
                    )
                )
    return out


def _has_word(haystack: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", haystack) is not None


def verdict(findings: list[Finding]) -> bool:
    """Does this generated text pass the grounding gate? Warnings do not fail it."""
    return not any(f.severity is Severity.ERROR for f in findings)
