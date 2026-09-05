"""Making beats: the source's sentences, and the scaffolding around them.

Two kinds of beat come out of here and the difference matters more than anything else in this
module. **Exposition** is the paper talking; every one of those beats carries the span it came
from (rule GRD-01) and its text is the verbalized source, never a rewrite. **Scaffolding** is
mimem talking -- orientation, position statements, prompts, recaps, transitions -- and every one
of those is a named template, marked ``generated``, so a listener is never in doubt about whose
claim they just heard (rule VOI-02) and a reader of ``manifest.json`` is never in doubt about
who wrote a sentence.

All of it, template text included, goes through the stage 5 verbalizers before it reaches a
beat. That is not a formality: ``ORI-01``'s own example is "Section 3 of 7", which is two lint
errors as written. Scaffolding is speech and has to obey the same rules the source does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from mimem.config import Listener, Profile
from mimem.ir import (
    Beat,
    BeatType,
    Block,
    BlockKind,
    Card,
    Concept,
    PromptType,
    Provenance,
    Span,
    TriageAction,
    beat_id,
)
from mimem.plan.support import Support
from mimem.verbalize import verbalize_block, verbalize_text

#: Target speech length of one exposition beat, in seconds. Short enough that a segment is
#: several beats -- the planner needs somewhere to cut (SEG-01) and something to re-synthesise
#: incrementally (TTS-03) -- long enough that a beat is still an argument, not a fragment.
BEAT_TARGET_SECONDS = 22.0

#: Number words, so the scaffolding can count out loud (rule SIG-01) without digits.
_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
)


@dataclass
class BeatFactory:
    """Builds beats, verbalizing template text and keeping IDs unique.

    IDs are content-addressed (rule TTS-03) so that re-rendering an edited document only
    re-synthesises what changed. Genuinely identical text -- two "take a few seconds" cues --
    gets a disambiguating salt, because those are two chunks of audio, not one.
    """

    profile: Profile
    listener: Listener | None = None
    strip_superscripts: bool = False
    _seen: dict[str, int] = field(default_factory=dict)

    def speak(self, text: str) -> str:
        """Run text through the stage 5 verbalizers. Scaffolding included."""
        return verbalize_text(
            text, self.profile, self.listener, strip_superscripts=self.strip_superscripts
        ).strip()

    @staticmethod
    def _closed(text: str) -> str:
        """Close a beat on a sentence boundary (rule TTS-04).

        Source text does not always oblige: a caption, a list item or a table cell often has no
        final period. Adding one is a rendering decision, not a change of content -- an engine
        given an unterminated clause runs it into the next beat and the boundary disappears.
        """
        # Leading punctuation is what the citation and cross-reference strippers leave behind:
        # "Figure 1. Discharge capacity..." loses its label and opens on a full stop.
        stripped = re.sub(r"^[\s.,;:\u2014-]+", "", text.strip())
        if stripped and stripped[-1] not in ".?!:;\u2014":
            return stripped + "."
        return stripped

    def make(
        self,
        beat_type: BeatType,
        text: str,
        *,
        verbalize: bool = True,
        spans: list[Span] | None = None,
        concept_ids: list[str] | None = None,
        rules: list[str] | None = None,
        pause_after: float = 0.0,
        generated: bool | None = None,
        generator: str | None = None,
        written_text: str | None = None,
        card_id: str | None = None,
    ) -> Beat:
        spoken = self._closed(self.speak(text) if verbalize else text)
        digest_key = f"{beat_type}:{spoken}"
        salt = str(self._seen.get(digest_key, 0))
        self._seen[digest_key] = self._seen.get(digest_key, 0) + 1
        is_generated = generated if generated is not None else not spans
        return Beat(
            id=beat_id(beat_type, spoken, salt),
            type=beat_type,
            text=spoken,
            written_text=written_text,
            spans=spans or [],
            concept_ids=concept_ids or [],
            rules=rules or [],
            est_seconds=self.profile.seconds_for(spoken),
            pause_after=pause_after,
            generated=is_generated,
            provenance=Provenance(generator=generator or "template") if is_generated else None,
            card_id=card_id,
        )


# -- exposition --------------------------------------------------------------------------


def exposition_beats(
    block: Block,
    factory: BeatFactory,
    patterns: dict[str, re.Pattern[str]],
    skip: set[tuple[str, int, int]] | None = None,
) -> list[Beat]:
    """The source's own sentences, verbalized and cut into beat-sized pieces.

    Cut at sentence boundaries only. A beat boundary is a place the planner may later put a
    pause, a prompt or a segment break, and cutting mid-sentence would make every one of those
    an error (rules SEG-01, TTS-04).

    ``skip`` names sentences the opening has already spoken, by span. They are dropped here
    rather than filtered out later, because a beat covers several sentences: matching whole
    beats against one sentence found nothing, and the paper's framing sentence was read out
    twice, forty seconds apart.
    """
    skip = skip or set()
    transformed = block.triage is not None and block.triage.action is TriageAction.TRANSFORM
    if transformed or block.kind in {
        BlockKind.TABLE,
        BlockKind.FIGURE,
        BlockKind.EQUATION,
        BlockKind.CODE,
    }:
        # Triage marks a block TRANSFORM when its meaning is not in its words -- a nomenclature
        # table, a paragraph built around symbols the PDF never carried. Reading those as prose
        # produces "a quantity, a quantity, a quantity", which is worse than saying nothing.
        return _non_prose_beat(block, factory, patterns)

    spans = block.sentences or [(0, len(block.text))]
    out: list[Beat] = []
    batch: list[tuple[int, int]] = []
    seconds = 0.0

    def flush() -> None:
        nonlocal batch, seconds
        if not batch:
            return
        start, end = batch[0][0], batch[-1][1]
        raw = block.text[start:end].strip()
        spoken = factory.speak(raw)
        if spoken:
            out.append(
                factory.make(
                    BeatType.EXPOSITION,
                    spoken,
                    verbalize=False,
                    spans=[
                        Span(block_id=block.id, char_start=start, char_end=end, page=block.page)
                    ],
                    concept_ids=[cid for cid, pattern in patterns.items() if pattern.search(raw)],
                    rules=["STR-04"],
                    written_text=raw,
                    generated=False,
                )
            )
        batch, seconds = [], 0.0

    for start, end in spans:
        sentence = block.text[start:end]
        if not sentence.strip():
            continue
        if (block.id, start, end) in skip:
            flush()  # do not weld the sentences either side of the gap into one beat
            continue
        batch.append((start, end))
        seconds += factory.profile.seconds_for(sentence)
        if seconds >= BEAT_TARGET_SECONDS:
            flush()
    flush()
    return out


def _non_prose_beat(
    block: Block, factory: BeatFactory, patterns: dict[str, re.Pattern[str]]
) -> list[Beat]:
    """A figure, table, equation or listing: the honest placeholder until M5's verbalizers."""
    spoken = verbalize_block(
        block, factory.profile, factory.listener, strip_superscripts=factory.strip_superscripts
    )
    if not spoken.strip():
        return []
    types = {
        BlockKind.TABLE: BeatType.TABLE,
        BlockKind.FIGURE: BeatType.FIGURE,
        BlockKind.EQUATION: BeatType.EQUATION,
        BlockKind.CODE: BeatType.EQUATION,
    }
    return [
        factory.make(
            types.get(block.kind, BeatType.EXPOSITION),
            spoken,
            verbalize=False,
            spans=[block.span()],
            concept_ids=[cid for cid, p in patterns.items() if p.search(block.text)],
            rules=["TBL-01" if block.kind is BlockKind.TABLE else "FIG-01"],
            written_text=block.text,
            generated=False,
        )
    ]


# -- scaffolding -------------------------------------------------------------------------


def orientation_beat(
    factory: BeatFactory,
    title: str,
    authors: list[str],
    minutes: float,
    problem: Support | None,
    promises: list[Concept],
) -> Beat:
    """Rule STR-01: what this is, who wrote it, why anyone cared, what you will be able to say.

    "Why anyone cared" is the paper's own framing sentence, not ours -- so the beat carries a
    span for that part and is still marked generated, because the sentences around it are.
    """
    parts = [f"This is {title.rstrip('.')}."]
    if authors:
        named = authors[0] if len(authors) == 1 else f"{authors[0]} and colleagues"
        parts.append(f"It's by {named}.")
    if problem is not None:
        parts.append(f"Here's the problem they set out from. {problem.spoken}")
    if promises:
        names = _list_of(c.canonical for c in promises[:3])
        parts.append(f"By the end you should be able to say what {names} are, and why they matter.")
    parts.append(f"It'll take about {round(minutes)} minutes.")
    return factory.make(
        BeatType.ORIENTATION,
        " ".join(parts),
        spans=[problem.span] if problem else None,
        concept_ids=[c.id for c in promises[:3]],
        rules=["STR-01"],
        generated=True,
        generator="template:orientation",
        pause_after=factory.profile.pauses.segment_boundary,
    )


def prequestion_beats(factory: BeatFactory, cards: list[Card]) -> list[Beat]:
    """Rules STR-02 and PRQ-01: two to four questions from the card pool, held open."""
    if not cards:
        return []
    lead = (
        f"Before we start, here are {_count(len(cards))} questions to hold on to. "
        "You're not meant to know the answers yet."
    )
    beats = [
        factory.make(
            BeatType.PREQUESTION,
            lead,
            rules=["STR-02"],
            generated=True,
            generator="template:prequestion-lead",
        )
    ]
    for i, card in enumerate(cards):
        beats.append(
            factory.make(
                BeatType.PREQUESTION,
                f"{_ORDINALS[i].capitalize()}. {card.prompt}",
                concept_ids=[card.concept_id] if card.concept_id else [],
                rules=["STR-02", "PRQ-01", "PAU-01"],
                pause_after=factory.profile.pauses.imagery_min,
                generated=True,
                generator="template:prequestion",
                card_id=card.id,
            )
        )
    return beats


def prequestion_close_beat(factory: BeatFactory, card: Card) -> Beat:
    """Rule PRQ-02: a prequestion is explicitly closed when its answer arrives.

    The answer itself was just said, by the beat before this one. Repeating it here would be
    the verbatim repetition rule ``REP-01`` forbids, thirty seconds apart. Closing the loop is
    the whole job: the listener needs to know the question they were holding is now discharged.
    """
    return factory.make(
        BeatType.PREQUESTION_CLOSE,
        f"That was one of the questions I asked at the start, the one about {card.subject}.",
        concept_ids=[card.concept_id] if card.concept_id else [],
        rules=["PRQ-02"],
        generated=True,
        generator="template:prequestion-close",
        card_id=card.id,
    )


def preload_beats(factory: BeatFactory, terms: list[tuple[Concept, str]]) -> list[Beat]:
    """Rule STR-03: at most seven terms, one line each, before the exposition starts."""
    if not terms:
        return []
    beats = [
        factory.make(
            BeatType.PRELOAD,
            f"First, {_count(len(terms))} words you'll need.",
            rules=["STR-03", "SIG-01"],
            generated=True,
            generator="template:preload-lead",
        )
    ]
    for concept, gloss in terms:
        beats.append(
            factory.make(
                BeatType.PRELOAD,
                f"{concept.canonical}. {gloss}",
                concept_ids=[concept.id],
                rules=["STR-03", "PRE-01"],
                generated=True,
                generator="template:preload",
            )
        )
    return beats


def position_beat(factory: BeatFactory, title: str, index: int, total: int) -> Beat:
    """Rule ORI-01: a one-clause position statement, so nobody is lost.

    "Part", not "section", and the reason is worth keeping: the stage 5 cross-reference stripper
    deletes "Section 3" wherever it appears, because rule ``STR-08`` says the audio track never
    points at something the listener cannot turn to. It deleted it here too, and the first real
    build opened every section with "of twenty one." Scaffolding does not get an exemption from
    the rules it exists to serve.
    """
    label = _strip_numbering(title) or "the next part"
    return factory.make(
        BeatType.POSITION,
        f"Part {index} of {total}. {label}.",
        rules=["ORI-01", "STR-04"],
        generated=True,
        generator="template:position",
        pause_after=factory.profile.pauses.section_boundary,
    )


def transition_beat(
    factory: BeatFactory,
    next_concept: Concept | None,
    section_title: str,
    *,
    is_new: bool = True,
) -> Beat:
    """Rule SEG-02: an audible boundary that carries information rather than filler (VOI-03).

    Three forms, in descending order of how much they tell the listener: the next thing is new,
    the next thing is more about something they have met, or -- when the planner has nothing to
    name -- simply that the section continues.
    """
    if next_concept is not None:
        text = (
            f"Next, {next_concept.canonical}." if is_new else f"More on {next_concept.canonical}."
        )
    else:
        text = f"Still on {_spoken_title(section_title)}."
    return factory.make(
        BeatType.TRANSITION,
        text,
        concept_ids=[next_concept.id] if next_concept else [],
        rules=["SEG-02", "PAU-03"],
        pause_after=factory.profile.pauses.segment_boundary,
        generated=True,
        generator="template:transition",
    )


def emphasis_beat(factory: BeatFactory, concept: Concept) -> Beat:
    """Rule SIG-02: at most one per section, so the marker keeps its force."""
    return factory.make(
        BeatType.EMPHASIS,
        f"This next part is the core of it, and it's about {concept.canonical}.",
        concept_ids=[concept.id],
        rules=["SIG-02"],
        generated=True,
        generator="template:emphasis",
    )


def recap_beat(factory: BeatFactory, concepts: list[Concept], section_title: str) -> Beat:
    """Rule STR-06: three sentences at most, naming what was met rather than restating it.

    A template cannot paraphrase, and repeating the section's sentences verbatim is exactly what
    rule REP-01 forbids. Naming the concepts is a genuinely different level of abstraction --
    the one-line summary that rule REP-01 asks a repeat to be.

    The concepts must be the ones *this section* introduced, not the document's highest scorers.
    Ranking globally made every recap in a paper about gradient boosting say "gradient boosting"
    first, which is both useless and, correctly, a ``REP-01`` violation seventeen times over.
    """
    names = _list_of(c.canonical for c in concepts[:3])
    spoken_title = _spoken_title(section_title)
    text = f"So, {spoken_title} in one line: {names}." if names else f"That was {spoken_title}."
    return factory.make(
        BeatType.RECAP,
        text,
        concept_ids=[c.id for c in concepts[:3]],
        rules=["STR-06"],
        generated=True,
        generator="template:recap",
    )


def callback_beat(factory: BeatFactory, concept: Concept, support: Support | None) -> Beat | None:
    """A spaced re-exposure (rules SPC-02, REP-01), or ``None`` when there is nothing to say.

    The sentence is a *different* thing the source says about the concept, never the one already
    used. When the source has nothing left, there is no callback: an earlier version emitted
    "keep this in mind, it comes back", which carries no claim, no span and no information, and
    rule ``GRD-01`` was right to reject it. A spaced exposure that teaches nothing is not worth
    the listener's minute; the missed exposure is recorded for part two instead.
    """
    if support is None:
        return None
    return factory.make(
        BeatType.CALLBACK,
        f"Back to {concept.canonical} for a moment. {support.spoken}",
        verbalize=False,
        spans=[support.span],
        concept_ids=[concept.id],
        rules=["SPC-02", "REP-01"],
        written_text=support.written,
        generated=False,
    )


def prompt_beats(factory: BeatFactory, card: Card, *, review: bool = False) -> list[Beat]:
    """Rules RET-01 and PAU-01: prompt, then a pause with an explicit cue, then the answer.

    The cue is spoken rather than encoded as a break marker. An engine that ignores a break
    marker turns a retrieval attempt into a sentence the listener hears and forgets; an engine
    that ignores "take a few seconds" has still told the listener to take them.
    """
    pauses = factory.profile.pauses
    answer_seconds = factory.profile.seconds_for(card.answer)
    pause = min(max(pauses.retrieval_min, answer_seconds * 0.5), pauses.retrieval_max)
    concept_ids = [card.concept_id] if card.concept_id else []
    prompt = factory.make(
        BeatType.PROMPT,
        f"{card.prompt} Take a few seconds.",
        concept_ids=concept_ids,
        rules=["RET-01", "RET-02", "PAU-01"] + (["STR-07", "SPC-04"] if review else ["RET-03"]),
        pause_after=pause,
        generated=True,
        generator="template:prompt",
        card_id=card.id,
    )
    answer = factory.make(
        BeatType.ANSWER,
        card.answer,
        verbalize=False,
        spans=list(card.spans),
        concept_ids=concept_ids,
        rules=["RET-01", "RET-04"],
        generated=False,
        card_id=card.id,
    )
    return [prompt, answer]


def review_lead_beat(factory: BeatFactory, n: int) -> Beat:
    """Rule STR-07: the review block announces itself (SIG-01) and interleaves (SPC-04)."""
    return factory.make(
        BeatType.REVIEW,
        f"That's the paper. Now {_count(n)} questions across all of it, in mixed order.",
        rules=["STR-07", "SPC-04", "SIG-01"],
        pause_after=factory.profile.pauses.section_boundary,
        generated=True,
        generator="template:review-lead",
    )


# -- cards -------------------------------------------------------------------------------


def topic_card(
    title: str,
    support: Support,
    section_id: str | None,
    profile: Profile,
    listener: Listener | None = None,
) -> Card:
    """A closing question for a section the extractor found no concept in (rule STR-06).

    Response-congruent by the same argument as everywhere else: this asks what the section said,
    and the answer is what the section said, in the source's own words and with its span.
    """
    subject = _spoken_title(title)
    question = f"What did the part on {subject} say?"
    return Card(
        id="k_" + beat_id(BeatType.PROMPT, question, support.span.block_id)[2:],
        concept_id=None,
        subject=subject,
        prompt=verbalize_text(question, profile, listener).strip(),
        answer=verbalize_text(f"Here's the answer about {subject}.", profile, listener).strip()
        + f" {support.spoken}",
        prompt_type=PromptType.RECALL,
        section_id=section_id,
        spans=[support.span],
    )


def make_card(
    concept: Concept,
    support: Support,
    section_id: str | None,
    profile: Profile,
    listener: Listener | None = None,
) -> Card:
    """Build a response-congruent prompt and its answer (rules RET-02, RET-04, RET-05).

    Congruence is decided by what the supporting sentence *is*: a definitional sentence gets a
    "what does it mean" question, a causal one gets a "what explains it" question, a sentence
    carrying the concept's measured value gets a "what value" question. Asking for a mechanism
    and answering with a definition is the failure this is written to avoid.
    """
    term = concept.canonical
    if support.definitional:
        prompt_type = PromptType.DEFINITION
        question = f"What does {term} mean?"
    elif support.causal:
        prompt_type = PromptType.MECHANISM
        question = f"What did the paper say explains {term}?"
    elif re.search(r"\d", support.written):
        prompt_type = PromptType.VALUE
        question = f"What did they report for {term}?"
    else:
        prompt_type = PromptType.RECALL
        question = f"What did the paper say about {term}?"

    answer = (
        verbalize_text(f"Here's the answer about {term}.", profile, listener).strip()
        + f" {support.spoken}"
    )
    return Card(
        # Salted with the supporting span: two sections may legitimately ask about one concept,
        # and two cards with the same id would collide in cards.json and in the review block.
        id="k_" + beat_id(BeatType.PROMPT, question, f"{term}:{support.span.block_id}")[2:],
        concept_id=concept.id,
        subject=term,
        prompt=verbalize_text(question, profile, listener).strip(),
        answer=answer,
        prompt_type=prompt_type,
        difficulty=concept.difficulty,
        section_id=section_id,
        spans=[support.span],
    )


# -- small helpers -----------------------------------------------------------------------


def _list_of(items: Iterable[str]) -> str:
    """Spoken enumeration: "a, b and c", with no serial comma before "and"."""
    values = [i.strip() for i in items if i.strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" and {values[-1]}"


def _strip_numbering(title: str) -> str:
    """A heading without the source's own numbering.

    "1. Introduction" is "Part two of three. one. Introduction." if you skip this: the number is
    the *document's* section numbering, which is not the position the listener is at, and it is
    read aloud as a word by the number verbalizer.
    """
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[.)-]?\s*", "", title.strip()).rstrip(".")


def _spoken_title(title: str) -> str:
    """A heading, said mid-sentence. Numbered headings keep their words, not their numbering."""
    cleaned = _strip_numbering(title)
    if not cleaned:
        return "this part"
    # Leave an acronym or a proper noun alone; lowercase a sentence-cased heading so that it
    # reads as part of the sentence around it rather than as a label.
    head, _, rest = cleaned.partition(" ")
    if head.isupper() or (rest and any(w[:1].isupper() for w in rest.split())):
        return cleaned
    return cleaned[0].lower() + cleaned[1:]


def _count(n: int) -> str:
    """A small count as a word. The verbalizers would do it, but scaffolding reads better
    when the template already knows it is speech."""
    words = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
    return words[n] if 0 <= n < len(words) else str(n)
