"""Lint rules over the script: structure, timing, retrieval and spacing.

The rules in :mod:`mimem.lint.rules` read the narration text and catch everything that would be
unspeakable. These read the plan, and catch everything that would be unmemorable: a section that
never asks you anything, a segment carrying five new terms, a repeat that is the same sentence
twice, a concept met three times inside a minute and then never again.

They are written to be **independent of the planner**. Nothing here reads a field the planner
filled in to say what it intended; every rule recomputes what it needs from the beats that
actually exist. A linter that trusts the planner's bookkeeping tests that the planner is
self-consistent, which is not the property anyone wants.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from itertools import pairwise

from mimem.config import Profile
from mimem.ir import TEACHING_TYPES, BeatType, ExposureForm, Script
from mimem.lint.rules import Severity, Violation
from mimem.plan.exposure import exposure_log, spaced

#: A shared run of this many words is verbatim repetition, not paraphrase (rule REP-01).
VERBATIM_NGRAM = 8

#: Word-overlap above this is near-verbatim even without a shared run.
VERBATIM_OVERLAP = 0.7


class ScriptRule(ABC):
    """A rule that reads the plan rather than the text."""

    id: str
    description: str
    severity: Severity = Severity.ERROR

    def __init__(self, profile: Profile | None = None) -> None:
        self.profile = profile or Profile(name="study")

    @abstractmethod
    def check(self, script: Script) -> list[Violation]:
        """Return every violation of this rule in ``script``."""

    def _violation(self, message: str, excerpt: str = "", beat_id: str | None = None) -> Violation:
        return Violation(
            rule=self.id,
            message=message,
            excerpt=excerpt[:160],
            severity=self.severity,
            beat_id=beat_id,
        )


# -- structure -------------------------------------------------------------------------------


class PrequestionsFromCards(ScriptRule):
    """STR-02: prequestions come from the retrieval pool, never invented for the opening.

    A curiosity hook that is never answered is the failure this prevents. The knowledge base is
    specific (§4.5): prequestions work when they are *about the material you are about to hear*,
    which is exactly what "drawn from cards.json" operationalises.
    """

    id = "STR-02"
    description = "every prequestion is a card, and every prequestion is closed"

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        card_ids = {c.id for c in script.cards}
        asked = [b for b in script.opening if b.type is BeatType.PREQUESTION and b.card_id]
        closed = {b.card_id for b in script.beats() if b.type is BeatType.PREQUESTION_CLOSE}

        # PRQ-01 asks for two to four. A document with one retrieval item cannot supply two,
        # and inventing one would break the rule this check exists to enforce.
        low = min(2, len(script.cards))
        if script.cards and not low <= len(asked) <= 4:
            out.append(
                self._violation(
                    f"{len(asked)} prequestions from {len(script.cards)} cards; "
                    "rule PRQ-01 asks for two to four"
                )
            )
        for beat in asked:
            if beat.card_id not in card_ids:
                out.append(
                    self._violation("prequestion is not in the card pool", beat.text, beat.id)
                )
            elif beat.card_id not in closed:
                out.append(
                    self._violation("prequestion is never closed (rule PRQ-02)", beat.text, beat.id)
                )
        return out


class SectionEndsWithRecapAndPrompt(ScriptRule):
    """STR-06: every section ends with a micro-recap and one retrieval prompt."""

    id = "STR-06"
    description = "each section ends with a recap and a prompt"

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for section in script.sections:
            types = [b.type for b in section.beats()]
            if BeatType.RECAP not in types:
                out.append(self._violation(f"section {section.title!r} has no recap"))
            if BeatType.PROMPT not in types:
                out.append(self._violation(f"section {section.title!r} has no retrieval prompt"))
        return out


class ReviewIsInterleaved(ScriptRule):
    """STR-07 and SPC-04: the review block mixes sections, and only the review block does."""

    id = "STR-07"
    description = "review items alternate between sections"

    def check(self, script: Script) -> list[Violation]:
        prompts = [b for b in script.review if b.type is BeatType.PROMPT and b.card_id]
        sections = []
        for beat in prompts:
            card = script.card(beat.card_id or "")
            sections.append(card.section_id if card else None)
        out: list[Violation] = []
        for previous, current in pairwise(sections):
            if previous is not None and previous == current:
                out.append(self._violation(f"two consecutive review items from section {previous}"))
        return out


class SegmentDuration(ScriptRule):
    """SEG-01: segments stay inside the duration bounds, and split at beat boundaries."""

    id = "SEG-01"
    description = "segment duration within the profile's bounds"

    def check(self, script: Script) -> list[Violation]:
        bounds = self.profile.segments
        out: list[Violation] = []
        for section in script.sections:
            for i, segment in enumerate(section.segments):
                seconds = segment.est_seconds
                if seconds > bounds.hard_max:
                    out.append(
                        self._violation(
                            f"segment {segment.id} runs {seconds:.0f}s, over the "
                            f"{bounds.hard_max:.0f}s hard maximum"
                        )
                    )
                elif seconds > bounds.target_max:
                    out.append(
                        Violation(
                            rule=self.id,
                            message=f"segment {segment.id} runs {seconds:.0f}s, over the "
                            f"{bounds.target_max:.0f}s target",
                            excerpt="",
                            severity=Severity.WARNING,
                        )
                    )
                elif seconds < bounds.target_min and i < len(section.segments) - 1:
                    out.append(
                        Violation(
                            rule=self.id,
                            message=f"segment {segment.id} runs only {seconds:.0f}s",
                            excerpt="",
                            severity=Severity.WARNING,
                        )
                    )
        return out


class NewTermBudget(ScriptRule):
    """SEG-03: at most a few new terms per segment.

    This is the working-memory rule (knowledge base §2.2), and the one that a planner optimising
    for coverage will break first: it is always tempting to fit one more idea into the segment
    you already have.
    """

    id = "SEG-03"
    description = "new terms per segment within the profile's budget"

    def check(self, script: Script) -> list[Violation]:
        limit = self.profile.max_new_terms_per_segment
        seen: set[str] = set()
        out: list[Violation] = []
        for section in script.sections:
            for segment in section.segments:
                taught = [
                    c
                    for beat in segment.beats
                    if beat.type in TEACHING_TYPES
                    for c in beat.concept_ids
                ]
                introduced = list(dict.fromkeys(c for c in taught if c not in seen))
                # A single sentence carrying more new terms than the budget cannot be split
                # without splitting the sentence, which rules SEG-01 and TTS-04 forbid. That is
                # a property of the source, reported as a warning; anything else is the planner
                # over-packing a segment, which is an error it could have avoided.
                worst = max(
                    (
                        len([c for c in b.concept_ids if c not in seen])
                        for b in segment.beats
                        if b.type in TEACHING_TYPES
                    ),
                    default=0,
                )
                seen.update(introduced)
                if len(introduced) <= limit:
                    continue
                names = ", ".join(
                    script.registry[c].canonical for c in introduced if c in script.registry
                )
                unavoidable = worst > limit
                out.append(
                    Violation(
                        rule=self.id,
                        message=(
                            f"segment {segment.id} introduces {len(introduced)} new terms, over "
                            f"the budget of {limit}"
                            + (" (one beat carries them all)" if unavoidable else "")
                        ),
                        excerpt=names[:160],
                        severity=Severity.WARNING if unavoidable else Severity.ERROR,
                    )
                )
        return out


# -- retrieval and pacing ----------------------------------------------------------------------


class PromptHasAnswer(ScriptRule):
    """RET-01: a prompt without an answer is a question the listener cannot resolve."""

    id = "RET-01"
    description = "every prompt is followed by its answer"

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for run in (script.opening, *[s.beats() for s in script.sections], script.review):
            for i, beat in enumerate(run):
                if beat.type is not BeatType.PROMPT:
                    continue
                following = run[i + 1] if i + 1 < len(run) else None
                if following is None or following.type is not BeatType.ANSWER:
                    out.append(self._violation("prompt has no answer beat", beat.text, beat.id))
        return out


class PromptHasPause(ScriptRule):
    """PAU-01: a retrieval prompt is followed by silence, and by a cue that says so.

    Without the pause the prompt is a rhetorical question, and rhetorical questions produce none
    of the retrieval benefit the whole design is built on (knowledge base §1.1).
    """

    id = "PAU-01"
    description = "every prompt is followed by a pause of the configured length"

    def check(self, script: Script) -> list[Violation]:
        floor = self.profile.pauses.retrieval_min
        out: list[Violation] = []
        for beat in script.beats():
            if beat.type is BeatType.PROMPT and beat.pause_after < floor:
                out.append(
                    self._violation(
                        f"pause of {beat.pause_after:.1f}s, under the {floor:.1f}s minimum",
                        beat.text,
                        beat.id,
                    )
                )
        return out


class RepeatsAreNotVerbatim(ScriptRule):
    """REP-01: a repeat is a different sentence, not the same one again.

    Hearing the same words twice produces the fluency illusion -- the feeling of knowing, without
    the knowing (knowledge base §1.5). Two exposures sharing an eight-word run, or most of their
    vocabulary, are the same sentence with the serial numbers filed off.

    **Statements only.** A question asked at the end of its section and again in the review block
    is the same question on purpose: that is spaced retrieval, the mechanic the whole programme
    is built around, and rule ``REP-01`` is about restatement rather than about re-asking. The
    first version of this rule flagged twenty-five of them and was wrong every time.
    """

    id = "REP-01"
    description = "repeated statements about a concept are not verbatim"

    #: Forms this rule compares. Prompts are excluded; see the class docstring.
    FORMS = frozenset(
        {
            ExposureForm.STATEMENT.value,
            ExposureForm.CALLBACK.value,
            ExposureForm.RECAP.value,
            ExposureForm.ANCHOR.value,
        }
    )

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        by_id = {b.id: b for b in script.beats()}
        for concept_id, entries in exposure_log(script).items():
            texts = [
                (e.beat_id, by_id[e.beat_id].text)
                for e in entries
                if e.beat_id in by_id and e.form in self.FORMS
            ]
            for i, (beat_id, text) in enumerate(texts):
                for _, earlier in texts[:i]:
                    if _verbatim(text, earlier):
                        name = (
                            script.registry[concept_id].canonical
                            if concept_id in script.registry
                            else concept_id
                        )
                        out.append(
                            self._violation(
                                f"exposure of {name!r} repeats an earlier one verbatim",
                                text,
                                beat_id,
                            )
                        )
                        break
        return out


class MinimumSpacingGap(ScriptRule):
    """SPC-01: exposures of one concept are at least the minimum gap apart, and spread out.

    Measured over body exposures only, coalesced into episodes -- see
    :mod:`mimem.plan.exposure` for why both of those qualifications are needed for the rule to
    mean anything on a real document.

    **An error only when the planner chose the placement.** A callback exists because the
    spacing scheduler put it there, so a callback inside the minimum gap is a scheduling
    failure and fails the build. An introduction and the prompt that closes its section are put
    where they are by rules ``STR-04`` and ``STR-06``; in a paper whose sections run two minutes
    they cannot be three minutes apart, and no plan can make them so. Those are reported as a
    warning, because the information is worth having and the alternative -- dropping the
    section's only question, or moving it somewhere it does not belong -- is worse than the
    thing being reported.
    """

    id = "SPC-01"
    description = "spacing between exposures of the same concept"

    def check(self, script: Script) -> list[Violation]:
        min_gap = self.profile.spacing.min_gap_minutes * 60.0
        out: list[Violation] = []
        for concept_id, entries in exposure_log(script).items():
            episodes = spaced(entries, min_gap)
            name = (
                script.registry[concept_id].canonical
                if concept_id in script.registry
                else concept_id
            )
            for previous, current in pairwise(episodes):
                gap = current.at_seconds - previous.at_seconds
                if gap >= min_gap:
                    continue
                scheduled = current.form == ExposureForm.CALLBACK.value
                out.append(
                    Violation(
                        rule=self.id,
                        message=(
                            f"{name!r} met again after {gap / 60:.1f} min, under the "
                            f"{min_gap / 60:.0f} min minimum"
                            + ("" if scheduled else " (both placed by the structure rules)")
                        ),
                        excerpt="",
                        severity=Severity.ERROR if scheduled else Severity.WARNING,
                        beat_id=current.beat_id,
                    )
                )
        return out


# -- faithfulness and hand-off ------------------------------------------------------------------


class BeatsAreGrounded(ScriptRule):
    """GRD-01: a beat either points at the source or is typed as scaffolding.

    This is the rule that keeps the elaboration layer honest when it arrives: an LLM-written
    sentence can be an anchor or an analogy, and it can never be exposition.
    """

    id = "GRD-01"
    description = "beats carry source spans or are typed generated"

    def check(self, script: Script) -> list[Violation]:
        return [
            self._violation(f"{beat.type.value} beat has no source span", beat.text, beat.id)
            for beat in script.beats()
            if beat.needs_span and not beat.spans
        ]


class AnchorsAreUnique(ScriptRule):
    """IMG-02: one anchor per concept, and no two concepts share one.

    A shared anchor is worse than no anchor: it makes two ideas retrieve each other.
    """

    id = "IMG-02"
    description = "anchors are stable and unique across the registry"

    def check(self, script: Script) -> list[Violation]:
        seen: dict[str, str] = {}
        out: list[Violation] = []
        for concept in script.registry.values():
            if concept.anchor is None:
                continue
            key = " ".join(concept.anchor.text.lower().split())
            owner = seen.get(key)
            if owner is not None and owner != concept.canonical:
                out.append(
                    self._violation(
                        f"{concept.canonical!r} and {owner!r} share an anchor",
                        concept.anchor.text,
                    )
                )
            seen[key] = concept.canonical
        return out


class AnalogiesStateTheirLimit(ScriptRule):
    """ANA-01: an analogy says where it breaks, in the same breath.

    The model refuses to build one without a limit, so this rule is the second line of defence:
    it catches an analogy assembled around validation, and it will catch a model-written one in
    M5 whose "limit" is a restatement of the analogy rather than a limit.
    """

    id = "ANA-01"
    description = "every analogy states its limit"

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for concept in script.registry.values():
            analogy = concept.analogy
            if analogy is None:
                continue
            if not analogy.limit.strip():
                out.append(
                    self._violation(
                        f"analogy for {concept.canonical!r} states no limit", analogy.text
                    )
                )
            elif _overlap(analogy.limit, analogy.text) > VERBATIM_OVERLAP:
                out.append(
                    self._violation(
                        f"the stated limit for {concept.canonical!r} restates the analogy",
                        analogy.limit,
                    )
                )
        return out


class ChunksAlignWithSentences(ScriptRule):
    """TTS-04: a chunk never ends mid-sentence.

    Chunks are beats, so this holds by construction -- which is exactly why it is worth
    checking: the construction is what a future change would break.
    """

    id = "TTS-04"
    description = "beat text ends on a sentence boundary"

    def check(self, script: Script) -> list[Violation]:
        return [
            self._violation("beat does not end on a sentence boundary", beat.text, beat.id)
            for beat in script.beats()
            if beat.text.strip() and beat.text.strip()[-1] not in ".?!:;—"
        ]


#: The M4 script rule set, in report order.
SCRIPT_RULE_TYPES: tuple[type[ScriptRule], ...] = (
    PrequestionsFromCards,
    SectionEndsWithRecapAndPrompt,
    ReviewIsInterleaved,
    SegmentDuration,
    NewTermBudget,
    PromptHasAnswer,
    PromptHasPause,
    RepeatsAreNotVerbatim,
    MinimumSpacingGap,
    BeatsAreGrounded,
    AnchorsAreUnique,
    AnalogiesStateTheirLimit,
    ChunksAlignWithSentences,
)


def script_rules(profile: Profile | None = None) -> tuple[ScriptRule, ...]:
    """Instantiate the script rules against a profile, whose budgets several of them read."""
    return tuple(rule(profile) for rule in SCRIPT_RULE_TYPES)


# -- helpers ---------------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.lower())


def _overlap(a: str, b: str) -> float:
    wa, wb = set(_words(a)), set(_words(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _verbatim(a: str, b: str) -> bool:
    """Do these two say the same thing in the same words?"""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    if _overlap(a, b) > VERBATIM_OVERLAP:
        return True
    if min(len(wa), len(wb)) < VERBATIM_NGRAM:
        return False
    runs = {tuple(wa[i : i + VERBATIM_NGRAM]) for i in range(len(wa) - VERBATIM_NGRAM + 1)}
    return any(
        tuple(wb[i : i + VERBATIM_NGRAM]) in runs for i in range(len(wb) - VERBATIM_NGRAM + 1)
    )
