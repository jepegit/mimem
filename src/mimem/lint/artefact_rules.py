"""Lint rules that need more than one artefact to check.

The text rules read the narration. The script rules read the plan. These read *two things at
once* and check that the difference between them is the difference we intended.

That difference is the whole design. ``audio.md`` drops the exact value and speaks a chunked
approximation; ``study.md`` must still carry the exact one, or the reduction became a loss
(``NUM-06``). Triage drops the funding paragraph; the narration must not contain it anyway
(``COH-01``). An equation is cut for time; its LaTeX must still be written down somewhere a
reader can find it (``MTH-04``). None of these is visible from inside a single file, and each of
them is a way for the system to quietly stop keeping a promise it makes in the documentation.

They need the source document, which the other two families do not. A caller that has no
document gets a report saying so rather than a report that looks clean -- see
:class:`mimem.lint.runner.LintReport.skipped`. A rule that silently does not run is worse than a
rule that does not exist, because the summary line still says a number.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from mimem.config import Profile
from mimem.ir import (
    NON_CONTENT_ROLES,
    Beat,
    BeatType,
    Block,
    BlockKind,
    Document,
    Script,
    TriageAction,
)
from mimem.lint.rules import Severity, Violation

#: A sentence shorter than this proves nothing: "The results are shown." appears in a dropped
#: acknowledgements block and in the results section, and matching on it would report the
#: coincidence rather than the leak.
DISTINCTIVE_WORDS = 8


@dataclass(frozen=True)
class Bundle:
    """Everything one build produced, for the rules that compare two parts of it."""

    script: Script
    doc: Document
    audio: str
    study: str


class ArtefactRule(ABC):
    """A rule that reads more than one artefact."""

    id: str
    description: str
    severity: Severity = Severity.ERROR

    def __init__(self, profile: Profile | None = None) -> None:
        self.profile = profile or Profile(name="study")

    @abstractmethod
    def check(self, bundle: Bundle) -> list[Violation]:
        """Return every violation of this rule in ``bundle``."""

    def _violation(self, message: str, excerpt: str = "", beat_id: str | None = None) -> Violation:
        return Violation(
            rule=self.id,
            message=message,
            excerpt=" ".join(excerpt.split())[:160],
            severity=self.severity,
            beat_id=beat_id,
        )


class DropListRespected(ArtefactRule):
    """COH-01: what triage dropped did not come back.

    Two halves, because there are two ways to fail. The first asks whether the *pipeline*
    honoured its own decisions: every block triage marked as furniture, checked against the
    narration it should not be in. The second asks whether triage was *right*, by looking for
    the furniture itself -- funding sentences, competing-interest boilerplate, correspondence
    addresses -- in the finished audio, wherever it came from.

    The first half catches a planner that reads the wrong list. The second catches a document
    whose funding paragraph was never recognised as one, which is the more likely failure and
    the one that no amount of internal consistency would reveal.
    """

    id = "COH-01"
    description = "nothing on the default-drop list is narrated"

    #: The furniture itself, in the words it is usually written in (design rules section 6).
    FURNITURE = (
        (r"\bthis work was (?:supported|funded|financed)\b", "funding statement"),
        (r"\bwe (?:thank|are grateful)\b", "acknowledgement"),
        # "We acknowledge" needs its object, because it is two different sentences. "We
        # acknowledge support from the Research Council" is a credit; "we acknowledge that
        # artificial intelligence can play additional roles, but we narrow our focus" is a
        # concession, and ordinary scientific prose. The bare verb failed a real paper's build
        # -- an *error*, so it also refused to synthesise the audio -- over the second kind.
        (
            r"\bwe (?:gratefully |also )?acknowledge (?:the |their |generous |financial )*"
            r"(?:support|funding|assistance|help|contribution|use of|access to)\b",
            "acknowledgement",
        ),
        (r"\bthe authors declare\b", "competing-interests boilerplate"),
        (r"\bcorrespondence should be addressed\b", "correspondence address"),
        (r"\ball rights reserved\b", "copyright notice"),
        (r"\bunder (?:a )?creative commons\b", "licence notice"),
        (
            r"\bthe (?:remainder|rest) of this (?:paper|article|chapter) is organi[sz]ed\b",
            "roadmap paragraph",
        ),
        (r"\bkeywords\b\s*:", "keyword list"),
        (r"\bgrant (?:number|agreement)\b", "grant number"),
    )

    #: Page furniture: a running head or a folio, which no beat may ever quote.
    FURNITURE_KINDS = frozenset({BlockKind.PAGE_ARTIFACT, BlockKind.REFERENCE})

    def _on_the_list(self, block: Block) -> bool:
        """Is this block on COH-01's list, as opposed to merely dropped under its number?

        Triage also drops the title and the author line under ``COH-01``, and the reason it
        gives says why: the orientation block speaks them properly a moment later (``STR-01``).
        Those are *moved*, not dropped, and a rule that called the move a leak would be
        demanding that the programme never say what the paper is called.
        """
        return block.role in NON_CONTENT_ROLES or block.kind in self.FURNITURE_KINDS

    def check(self, bundle: Bundle) -> list[Violation]:
        out: list[Violation] = []
        spoken = _normalise(bundle.audio)

        for block in bundle.doc.blocks:
            decision = block.triage
            if decision is None or decision.action is not TriageAction.DROP:
                continue
            if decision.rule != self.id or not self._on_the_list(block):
                continue
            for sentence in _sentences(block.text):
                if len(sentence.split()) < DISTINCTIVE_WORDS:
                    continue
                if _normalise(sentence) in spoken:
                    out.append(
                        self._violation(
                            f"dropped as {decision.reason!r}, but narrated anyway", sentence
                        )
                    )
                    break

        for pattern, label in self.FURNITURE:
            match = re.search(pattern, bundle.audio, re.IGNORECASE)
            if match:
                out.append(self._violation(f"{label} reached the audio track", match.group(0)))
        return out


class EquationsSurviveInWriting(ArtefactRule):
    """MTH-04: every equation is in ``study.md``, whether or not it is spoken.

    An equation that was cut for time is still the most compressed statement of the thing the
    section is about, and a reader who wants it wants it exactly. Speech cannot carry it; the
    written track can, and it costs one line. So the test is not "was it narrated" but "can the
    reader get at it at all" -- which is why this rule reads ``study.md`` and not the script.
    """

    id = "MTH-04"
    description = "every equation in the source appears in study.md"

    def check(self, bundle: Bundle) -> list[Violation]:
        out: list[Violation] = []
        written = _normalise(bundle.study)
        for block in bundle.doc.by_kind(BlockKind.EQUATION):
            body = block.text.strip()
            if not body:
                continue
            if _normalise(body) not in written:
                out.append(
                    self._violation("equation is in the source but not in the written track", body)
                )
        return out


class ExactValuesSurviveInWriting(ArtefactRule):
    """NUM-06: reduction is audio-only.

    ``audio.md`` says "zero point zero eight, three seven percent"; it may, under a profile that
    asks for it, say "about zero point zero eight percent". Either way the listener is a
    researcher and the number is often the reason they are listening, so the exact digits have
    to be somewhere -- and ``study.md`` is where.

    Checked from the source side rather than the audio side. Going the other way would mean
    parsing spoken numbers back into digits, which is the one direction of the verbalizer that
    is not reliable; going this way asks the question that actually matters, which is whether
    any value the document stated has fallen out of both tracks.
    """

    id = "NUM-06"
    description = "every value in a narrated span has its exact form in study.md"

    #: Section numbers, years in citations and list markers are not values a listener needs
    #: back. A value worth checking has a decimal point, a unit after it, or is long enough
    #: that speech would have had to chunk it.
    VALUE = re.compile(
        r"\d+\.\d+|\d{4,}|\d+(?:\.\d+)?\s*(?:%|°|µ|nm|mm|cm|km|kg|mg|mA|mAh|V|W|Hz|K|C)\b"
    )

    def check(self, bundle: Bundle) -> list[Violation]:
        written = bundle.study
        seen: set[str] = set()
        out: list[Violation] = []
        for beat in bundle.script.beats():
            if beat.type is BeatType.PROMPT or not beat.spans:
                continue
            source = beat.written_text or _source_text(bundle.doc, beat)
            for match in self.VALUE.finditer(source):
                value = match.group(0).strip()
                if value in seen:
                    continue
                seen.add(value)
                if value not in written:
                    out.append(
                        self._violation(
                            f"value {value!r} is narrated but does not appear in study.md",
                            source,
                            beat.id,
                        )
                    )
        return out


#: The cross-artefact rule set, in report order.
ARTEFACT_RULE_TYPES: tuple[type[ArtefactRule], ...] = (
    DropListRespected,
    EquationsSurviveInWriting,
    ExactValuesSurviveInWriting,
)


def artefact_rules(profile: Profile | None = None) -> tuple[ArtefactRule, ...]:
    """Instantiate the cross-artefact rules against a profile."""
    return tuple(rule(profile) for rule in ARTEFACT_RULE_TYPES)


# -- helpers ---------------------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Collapse whitespace and case, so a line break is not a difference."""
    return " ".join(text.lower().split())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]


def _source_text(doc: Document, beat: Beat) -> str:
    """The document text a beat was written from, for beats that carry no ``written_text``."""
    parts: list[str] = []
    for span in beat.spans:
        try:
            parts.append(doc.text_of(span))
        except KeyError:  # a span into a block a later stage removed
            continue
    return " ".join(parts)
