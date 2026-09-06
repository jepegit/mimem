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
from mimem.plan.beats import OWNERSHIP_MARKERS
from mimem.plan.exposure import exposure_log, spaced
from mimem.verify import check as check_grounding

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


class GeneratedContentIsMarked(ScriptRule):
    """VOI-02: the listener always knows whose claim they just heard.

    An anchor and an analogy are ours. Said without a marker they are indistinguishable from the
    paper's own words, and the listener walks away attributing our cast-iron pan to a battery
    journal. This is the cheapest rule in the suite and one of the most important: everything
    else in the system is about being *useful*, and this one is about being *honest*.
    """

    id = "VOI-02"
    description = "generated content is introduced as generated"

    #: Beat types whose content is ours rather than the source's.
    OURS = frozenset({BeatType.ANCHOR, BeatType.ANALOGY})

    def check(self, script: Script) -> list[Violation]:
        return [
            self._violation(f"{beat.type.value} beat does not say it is ours", beat.text, beat.id)
            for beat in script.beats()
            if beat.type in self.OURS
            and not any(marker in beat.text.lower() for marker in OWNERSHIP_MARKERS)
        ]


class ImageryHasAPause(ScriptRule):
    """PAU-02: an image the listener is given no time to form is a sentence, not a picture."""

    id = "PAU-02"
    description = "anchors and analogies are followed by a pause"

    IMAGERY = frozenset({BeatType.ANCHOR, BeatType.ANALOGY})

    def check(self, script: Script) -> list[Violation]:
        floor = self.profile.pauses.imagery_min
        return [
            self._violation(
                f"pause of {beat.pause_after:.1f}s, under the {floor:.1f}s minimum",
                beat.text,
                beat.id,
            )
            for beat in script.beats()
            if beat.type in self.IMAGERY and beat.pause_after < floor
        ]


class GeneratedFactsAreGrounded(ScriptRule):
    """GRD-03, and ELB-03: the numbers and directions in generated text are the source's.

    Checked against the sentences the beat was written from, which the beat carries in
    ``written_text`` -- not against the whole document. A sentence that mixes up two unrelated
    results would pass a document-wide check, and that is exactly the plausible-sounding failure
    this rule exists for.

    Names are excluded here. The deterministic name check is a warning in
    :mod:`mimem.verify` for good reason, and an anchor is *supposed* to contain nouns the paper
    never used -- that is what an image for an abstract idea is.
    """

    id = "GRD-03"
    description = "numbers, years and directions in generated text match the source"

    #: Beat types written by a model rather than quoted from the document.
    WRITTEN = frozenset({BeatType.GLOSS, BeatType.ANCHOR, BeatType.ANALOGY, BeatType.ELABORATION})
    KINDS = frozenset({"number", "year", "direction"})

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for beat in script.beats():
            if beat.type not in self.WRITTEN or not beat.written_text:
                continue
            for finding in check_grounding(beat.text, beat.written_text):
                if finding.kind not in self.KINDS:
                    continue
                out.append(
                    self._violation(
                        f"{finding.kind} {finding.value!r}: {finding.message}",
                        beat.text,
                        beat.id,
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


class AnaphoraResolvesAcrossBeats(ScriptRule):
    """SENT-02: no unresolved pronoun at the start of a beat.

    Mid-paragraph, "it" is free: the antecedent is a line up and the reader's eye has not left
    it. A beat boundary is not a paragraph break -- it is a *chunk* boundary, and between two
    beats there may be a pause, a question, a retrieval attempt, or eleven minutes and another
    section. A beat that opens with "This means the layer keeps growing" is asking the listener
    to hold a referent across all of that, and the referent is the one thing they were not
    rehearsing.

    Only the opening of a beat is checked, and only pronouns in subject position. Everything
    further in has its antecedent inside the same breath, which is what ``SENT-02`` allows.

    Only the source's own sentences are checked. Our scaffolding says "that was one of the
    questions I asked at the start" and means the discourse, not a noun -- discourse deixis,
    which is how people actually talk and which points at something the listener heard four
    seconds ago on purpose. Nominal anaphora is the failure: a pronoun standing in for a noun
    phrase that a chunk boundary has since carried away.

    A warning, not an error, and deliberately so: these sentences are the *paper's*, quoted, and
    mimem has no rewriting stage that could fix one. Making it an error would fail every real
    document on a defect the system cannot yet repair -- which teaches a contributor to pass
    ``--no-lint``, the worst outcome available. It becomes an error when there is a rewriter to
    hold responsible.
    """

    id = "SENT-02"
    description = "no beat opens with a pronoun whose antecedent is in another beat"
    severity = Severity.WARNING

    #: Bare pronouns and demonstratives. A demonstrative followed by a noun ("this crust") is
    #: resolved by the noun and is not matched -- see ``_BARE`` below.
    _PRONOUNS = r"it|this|that|these|those|they|them|such"

    #: "It is worth noting", "it turns out", "there is no" -- the subject is grammatical filler
    #: and points at nothing, so there is nothing for the listener to have lost.
    EXPLETIVE = re.compile(
        r"^it\s+(?:is|was|turns\s+out|follows|remains|seems|appears|takes|helps|matters)\b",
        re.IGNORECASE,
    )

    #: A demonstrative counts as unresolved only when nothing follows it that could be the
    #: referent: "this is why" (bare) fails, "this repair" (determiner) passes.
    BARE = re.compile(
        r"^(?:" + _PRONOUNS + r")\s+(?:is|are|was|were|means|meant|gives|gave|shows|showed|gets|"
        r"got|gets|makes|made|gains|has|have|had|gets|gives|does|do|did|can|could|will|would|"
        r"gets|happens|explains|gets|becomes|became|comes|came|goes|went|stays|stayed|leaves|"
        r"left|costs|cost|matters|mattered|then|also|too|in|on|at|by|for|with|and|but|so)\b",
        re.IGNORECASE,
    )

    #: These two never resolve out loud whatever follows them, so they are matched on their own.
    ALWAYS = re.compile(r"^the\s+(?:former|latter|above|aforementioned)\b", re.IGNORECASE)

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for beat in script.beats():
            opening = beat.text.strip()
            if not opening or beat.generated:
                continue
            if self.EXPLETIVE.match(opening):
                continue
            match = self.ALWAYS.match(opening) or self.BARE.match(opening)
            if match:
                out.append(
                    self._violation(
                        f"beat opens with {match.group(0).split()[0].lower()!r}; "
                        "say the referent instead",
                        beat.text,
                        beat.id,
                    )
                )
        return out


class TableCaptionComesFirst(ScriptRule):
    """TBL-02: a table says what it is before it says what is in it.

    The listener cannot see that a list of values is coming, and cannot skim past it. Told
    first -- "this is a table of cell capacities at four temperatures" -- they can choose to
    stop attending, which is a *feature*: a listener who disengages knowingly comes back, and
    one who is ambushed by numbers loses the thread and does not.
    """

    id = "TBL-02"
    description = "a table beat opens by saying it is a table"

    #: Asked as a positive requirement rather than as a ban on numerals in the first sentence.
    #: The first draft banned them, and failed the caption "a table of capacity retention at
    #: four temperatures" -- where "four" counts the columns and is exactly the kind of thing a
    #: caption is *for*. What the listener needs is not the absence of a number, it is the
    #: presence of a frame, so that is what gets checked.
    ANNOUNCES = re.compile(
        r"\b(?:table|these (?:values|numbers|figures)|the (?:values|numbers|rows)|"
        r"row by row|column)\b",
        re.IGNORECASE,
    )

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for beat in script.beats():
            if beat.type is not BeatType.TABLE or not beat.text.strip():
                continue
            first = _first_sentence(beat.text)
            if not self.ANNOUNCES.search(first):
                out.append(
                    self._violation(
                        "table beat does not say it is a table before it says what is in it",
                        first,
                        beat.id,
                    )
                )
        return out


class FigureDescriptionFollowsTemplate(ScriptRule):
    """FIG-01: a figure description in the order a listener can build a picture from.

    Title-like statement, then what kind of figure, then axes and units, then the trend, then
    the exceptions, then the claim it supports (knowledge base 5.4). The order is not
    decoration: naming the kind before the axes tells the listener what shape of thing to hold
    the numbers in, and giving the claim last means they hear the evidence before the
    conclusion rather than filing the conclusion and stopping.

    mimem cannot yet *write* one of these -- that needs a vision model, and until it has one the
    planner emits an honest announcement instead ("there is a figure here, it is in the written
    notes"). So this rule checks descriptions and lets announcements through: a rule that failed
    the honest placeholder would be a rule against admitting what the system cannot do.
    """

    id = "FIG-01"
    description = "figure descriptions follow the accessibility template"
    severity = Severity.WARNING

    #: An announcement, not a description. Matched so it can be exempted.
    ANNOUNCEMENT = re.compile(
        r"\b(?:in the written notes|not described here|see the written|there'?s a figure|"
        r"there is a figure)\b",
        re.IGNORECASE,
    )

    #: FIG-01's second element: what kind of figure this is.
    KINDS = re.compile(
        r"\b(?:plot|graph|chart|diagram|schematic|micrograph|image|map|photograph|histogram|"
        r"scatter|curve|bar chart|flow ?chart)\b",
        re.IGNORECASE,
    )

    #: The third: what the axes carry. A figure whose axes are never named is a picture the
    #: listener cannot reconstruct.
    AXES = re.compile(
        r"\b(?:axis|axes|x[- ]axis|y[- ]axis|horizontal|vertical|against|versus)\b", re.IGNORECASE
    )

    TITLE_CHARS = 125

    def check(self, script: Script) -> list[Violation]:
        out: list[Violation] = []
        for beat in script.beats():
            if beat.type is not BeatType.FIGURE or not beat.text.strip():
                continue
            text = beat.text.strip()
            if self.ANNOUNCEMENT.search(text):
                continue
            first = _first_sentence(text)
            if len(first) > self.TITLE_CHARS:
                out.append(
                    self._violation(
                        f"opening statement is {len(first)} characters, "
                        f"over the {self.TITLE_CHARS}-character title cap",
                        first,
                        beat.id,
                    )
                )
            if not self.KINDS.search(text):
                out.append(
                    self._violation(
                        "description never says what kind of figure it is", text, beat.id
                    )
                )
            elif not self.AXES.search(text):
                out.append(
                    self._violation(
                        "description never names the axes or what is plotted against what",
                        text,
                        beat.id,
                    )
                )
        return out


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
    GeneratedContentIsMarked,
    ImageryHasAPause,
    GeneratedFactsAreGrounded,
    AnchorsAreUnique,
    AnalogiesStateTheirLimit,
    ChunksAlignWithSentences,
    AnaphoraResolvesAcrossBeats,
    TableCaptionComesFirst,
    FigureDescriptionFollowsTemplate,
)


def script_rules(profile: Profile | None = None) -> tuple[ScriptRule, ...]:
    """Instantiate the script rules against a profile, whose budgets several of them read."""
    return tuple(rule(profile) for rule in SCRIPT_RULE_TYPES)


# -- helpers ---------------------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    """The opening sentence, for the rules that care what a beat leads with."""
    stripped = text.strip()
    match = re.search(r"[.?!](?:\s|$)", stripped)
    return stripped[: match.end()].strip() if match else stripped


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
