"""The audio linter: the acceptance test for everything upstream.

Rules in ``docs/DESIGN-RULES.md`` are only real if something checks them. Each rule here is a
class with an ID that matches the design rule it enforces, so a failure points straight at the
paragraph of the specification it violates -- and at the evidence in the knowledge base behind
that paragraph.

This is the M2 subset: the rules that can be checked against narration text alone. The rules
about structure (prompts having answers, spacing intervals, anchors being unique) need the
script model and arrive with M4.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from mimem.clean.sentences import sentence_spans


class Severity(StrEnum):
    ERROR = "error"  # fails the build
    WARNING = "warning"  # reported, does not fail


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    excerpt: str
    severity: Severity = Severity.ERROR
    line: int | None = None
    beat_id: str | None = None  # set by the script rules, which have beats rather than lines


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _excerpt(text: str, start: int, end: int, pad: int = 32) -> str:
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    return " ".join(text[lo:hi].split())


class LintRule(ABC):
    id: str
    description: str
    severity: Severity = Severity.ERROR

    @abstractmethod
    def check(self, text: str) -> list[Violation]:
        """Return every violation of this rule in ``text``."""

    def _violation(self, text: str, start: int, end: int, message: str) -> Violation:
        return Violation(
            rule=self.id,
            message=message,
            excerpt=_excerpt(text, start, end),
            severity=self.severity,
            line=_line_of(text, start),
        )


class CharacterAllowlist(LintRule):
    """TTS-01: only speakable characters reach the engine.

    The allowlist is letters, whitespace and a small punctuation set. Apostrophes are in it
    because the generated voice uses contractions (rule VOI-01), and the hyphen is in it
    because removing it from "Li-ion" changes a term rather than a symbol.
    """

    id = "TTS-01"
    description = "audio text contains only speakable characters"
    ALLOWED_PUNCTUATION = ".,;:!?'-—"

    #: Digits and brackets are unspeakable too, but they belong to NUM-02 and SENT-03. Each
    #: defect should be reported once, by the rule that explains how to fix it.
    OWNED_ELSEWHERE = "0123456789()[]{}"

    def check(self, text: str) -> list[Violation]:
        out: list[Violation] = []
        for m in re.finditer(r"[^\w\s]|[\d_]", text):
            char = m.group(0)
            if char in self.ALLOWED_PUNCTUATION or char.isalpha():
                continue
            if char in self.OWNED_ELSEWHERE:
                continue
            out.append(self._violation(text, m.start(), m.end(), f"unspeakable character {char!r}"))
        return out


class NoRawNumerals(LintRule):
    """NUM-02: every number is words by the time it reaches the engine."""

    id = "NUM-02"
    description = "no raw digits in the audio track"

    def check(self, text: str) -> list[Violation]:
        return [
            self._violation(text, m.start(), m.end(), f"unverbalized number {m.group(0)!r}")
            for m in re.finditer(r"\d+(?:[.,]\d+)*", text)
        ]


class NoCitations(LintRule):
    """CIT-01: inline citations are suppressed."""

    id = "CIT-01"
    description = "no inline citations in the audio track"

    def check(self, text: str) -> list[Violation]:
        out: list[Violation] = []
        patterns = (
            (r"\[\s*\d", "bracketed citation"),
            (r"\bet\s+al\b", "'et al' should be 'and colleagues'"),
            (r"\bdoi\b", "DOI"),
            (r"https?://|www\.", "URL"),
        )
        for pattern, label in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                out.append(self._violation(text, m.start(), m.end(), label))
        return out


class NoParentheticals(LintRule):
    """SENT-03: parenthetical asides do not survive into speech."""

    id = "SENT-03"
    description = "no parentheses or brackets in the audio track"

    def check(self, text: str) -> list[Violation]:
        return [
            self._violation(text, m.start(), m.end(), "parenthetical")
            for m in re.finditer(r"[()\[\]{}]", text)
        ]


class NoVisualOnlyConstructs(LintRule):
    """SENT-04: things that only work on the page."""

    id = "SENT-04"
    description = "no written-only abbreviations or symbols"

    PATTERNS = (
        (r"\be\.\s?g\.", "'e.g.' must be 'for example'"),
        (r"\bi\.\s?e\.", "'i.e.' must be 'that is'"),
        (r"\bcf\.", "'cf.' must be 'compare'"),
        (r"\bvs\.", "'vs.' must be 'versus'"),
        (r"\betc\.", "'etc.' must be 'and so on'"),
        (r"§|¶|†|‡", "page-only mark"),
        (r"\b[A-Z]{2,}\b(?=[.,]?\s)", "unexpanded acronym"),
    )

    def check(self, text: str) -> list[Violation]:
        out: list[Violation] = []
        for pattern, label in self.PATTERNS:
            severity = Severity.WARNING if "acronym" in label else self.severity
            for m in re.finditer(pattern, text):
                out.append(
                    Violation(
                        rule=self.id,
                        message=label,
                        excerpt=_excerpt(text, m.start(), m.end()),
                        severity=severity,
                        line=_line_of(text, m.start()),
                    )
                )
        return out


class SentenceLength(LintRule):
    """SENT-01: a sentence a reader parses by re-scanning is simply lost in audio.

    Median at most 20 words, hard cap 35 (knowledge base 2.1). Reported as a warning: a long
    sentence is a quality problem, not a broken artefact, and the fix belongs to the rewriting
    stages that arrive in M4/M5.
    """

    id = "SENT-01"
    description = "sentences stay short enough to hold in working memory"
    severity = Severity.WARNING
    HARD_CAP = 35
    MEDIAN_TARGET = 20

    def check(self, text: str) -> list[Violation]:
        out: list[Violation] = []
        for start, end in sentence_spans(text):
            sentence = text[start:end]
            words = len(sentence.split())
            if words > self.HARD_CAP:
                out.append(
                    self._violation(
                        text, start, end, f"{words} words, over the {self.HARD_CAP}-word cap"
                    )
                )
        return out


class NoDanglingReferences(LintRule):
    """STR-08: nothing in the audio track points at something the listener cannot see.

    "As shown in the table below" is not merely useless in audio -- it tells the listener that
    they have missed something, which is worse than saying nothing at all. The cross-reference
    stripper in stage 5 removes the citation-shaped ones; this catches the prose-shaped ones it
    cannot see, and it will catch the first figure description that forgets where it is.
    """

    id = "STR-08"
    description = "no references to things the listener cannot access"

    _NOUNS = r"figure|table|equation|panel|plot|graph|chart"

    PATTERNS = (
        (
            r"\bsee\s+(?:the\s+)?(?:" + _NOUNS + r"|section|chapter|appendix)\b",
            "see-reference",
        ),
        (r"\b(?:" + _NOUNS + r")s?\s+(?:above|below)\b", "spatial reference"),
        (
            r"\bas\s+(?:shown|illustrated|listed|summari[sz]ed|depicted)"
            r"\s+(?:in|by)\s+the\s+(?:" + _NOUNS + r")\b",
            "visual reference",
        ),
        (
            r"\bin\s+the\s+(?:previous|preceding|following|next)"
            r"\s+(?:chapter|section)\b",
            "unreachable section",
        ),
        (r"\b(?:above|below)-mentioned\b", "spatial reference"),
    )

    def check(self, text: str) -> list[Violation]:
        out: list[Violation] = []
        for pattern, label in self.PATTERNS:
            out.extend(
                self._violation(text, m.start(), m.end(), label)
                for m in re.finditer(pattern, text, re.IGNORECASE)
            )
        return out


#: The text rule set, in report order. These read the narration; the structural rules that read
#: the plan live in ``script_rules.py``.
DEFAULT_RULES: tuple[LintRule, ...] = (
    CharacterAllowlist(),
    NoRawNumerals(),
    NoCitations(),
    NoParentheticals(),
    NoVisualOnlyConstructs(),
    NoDanglingReferences(),
    SentenceLength(),
)
