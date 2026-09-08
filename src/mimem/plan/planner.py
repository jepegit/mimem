"""Stage 7: turning a triaged document and a scored registry into a script.

This is where the design rules stop being a document and start being code. Every step below
names the rules it implements, and the order of the steps is itself load-bearing -- prompts must
exist before prequestions can be drawn from them (``STR-02``), the timeline must exist before
spacing can be measured on it (``SPC-01``), and the budget must be enforced before the spacing
repair pass because cutting beats moves everything that comes after them.

No model is called from here. Everything a listener hears is either a verbalized sentence of the
source, carrying its span, or a named template. That is a deliberate limit and not a temporary
one: structure, timing and retrieval are the parts of this system that can be checked, and the
elaboration layer in M5 is easier to trust when it is added to a plan that already holds.

What counts as an exposure -- the definition rule ``SPC-01`` needs and does not supply -- lives
in :mod:`mimem.plan.exposure`, so that the linter can recompute it instead of believing this
module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise

from mimem.concepts.registry import preload_terms
from mimem.config import Listener, Profile
from mimem.ir import (
    TEACHING_TYPES,
    Beat,
    BeatType,
    Block,
    BlockKind,
    BlockRole,
    Card,
    Concept,
    ConceptRegistry,
    Document,
    DropRecord,
    Exposure,
    ExposureForm,
    ScheduledReview,
    Script,
    Section,
    Segment,
    Span,
)
from mimem.plan import beats as make
from mimem.plan.budget import budget_seconds, enforce
from mimem.plan.exposure import COUNTED_FORMS, exposure_log, spaced
from mimem.plan.review import interleave
from mimem.plan.spacing import Request, Slot, repetitions_for, schedule
from mimem.plan.support import (
    Support,
    SupportPool,
    best_sentence,
    concept_pattern,
    gather,
)
from mimem.render.narrate import uses_superscript_citations
from mimem.triage.rules import retained

#: Prequestions: two to four per document (rule PRQ-01), whatever the profile asks for.
PREQUESTION_BOUNDS = (2, 4)

#: A group of retained blocks shorter than this is a fragment, not a section: it is folded into
#: the section above it. Rule STR-06 gives every section a recap and a question, and a heading
#: with twenty words under it can support neither -- on a real paper this produced a "section"
#: called "ES" with no concept in it at all. Sized just under the shortest segment a profile
#: asks for, so that a section is always at least one real segment.
MIN_SECTION_WORDS = 60

#: How many passes the spacing repair may take before it gives up and reports instead.
MAX_REPAIR_PASSES = 4


@dataclass
class _Context:
    """Everything the steps below share. Assembled once, never rebuilt."""

    doc: Document
    profile: Profile
    listener: Listener | None
    registry: ConceptRegistry
    factory: make.BeatFactory
    support: SupportPool
    patterns: dict[str, re.Pattern[str]]
    covered: set[tuple[str, int, int]] = field(default_factory=set)
    seen_concepts: set[str] = field(default_factory=set)
    announced: set[str] = field(default_factory=set)  # concepts a transition has already named
    elaborated: set[str] = field(default_factory=set)  # concepts whose gloss and anchor were said


def plan(
    doc: Document,
    registry: ConceptRegistry,
    profile: Profile,
    listener: Listener | None = None,
) -> Script:
    """Build the script for ``doc`` (PLAN section 4, stage 7)."""
    superscripts = uses_superscript_citations(doc)
    factory = make.BeatFactory(profile, listener, strip_superscripts=superscripts)
    concepts = dict(registry.concepts)
    ctx = _Context(
        doc=doc,
        profile=profile,
        listener=listener,
        registry=registry,
        factory=factory,
        support=gather(doc, concepts, profile, listener, strip_superscripts=superscripts),
        patterns={cid: concept_pattern(c) for cid, c in concepts.items()},
    )

    script = Script(
        doc_id=doc.id,
        source=doc.source,
        profile=profile.name,
        listener=listener.name if listener else None,
        registry={cid: c.model_copy(deep=True) for cid, c in concepts.items()},
    )

    # 1-2. sections, and the retrieval item each one will end on.
    groups = _section_groups(doc)
    script.cards = _card_pool(ctx, groups)
    by_section = {c.section_id: c for c in script.cards if c.section_id}
    prequestions = _prequestions(ctx, script.cards)

    # 3. the sentence the orientation will use for "why anyone cared", chosen *before* the
    # body so that the exposition can leave it out. Chosen after, it was said twice.
    problem = _problem_sentence(ctx)

    # 4-7. exposition, segmentation, emphasis, recaps, one prompt per section.
    script.sections = _body(ctx, groups, by_section, {c.id for c in prequestions})

    # 8. one retrieval prompt per segment where the budget allows (rules RET-03, ELB-02).
    # The section-closing cards are kept aside: they are what the review block interleaves.
    closing_cards = list(script.cards)
    script.budget_seconds = budget_seconds(
        _straight_read_seconds(script),
        profile.duration_multiplier,
        profile.duration_floor_seconds,
    )
    _add_segment_prompts(ctx, script)

    # 9. the opening block, which needs the cards and the body's duration.
    script.opening = _opening(ctx, script, prequestions, problem)

    # 10. spacing, measured on the timeline the opening and body produce. Everything the
    # exposition has already said is spent first, so a callback cannot hand back a sentence the
    # listener heard four minutes ago (rule REP-01).
    ctx.support.spend_covered(
        span
        for section in script.sections
        for beat in section.beats()
        if beat.type is BeatType.EXPOSITION
        for span in beat.spans
    )
    next_intervals = _place_callbacks(ctx, script)

    # 11. the review block: every section's question, interleaved (STR-07, SPC-04).
    script.review = _review(ctx, closing_cards)

    # 12. the duration budget, before the repair pass, because cutting moves the clock.
    #
    # Measured on the *verbalized* content, not the source text. "0.05 V" is two words on the
    # page and seven when spoken, so a budget derived from the raw text is systematically too
    # small -- and a budget that is always exceeded is a budget that cuts things nobody asked
    # it to cut.
    script.budget_seconds = budget_seconds(
        _straight_read_seconds(script),
        profile.duration_multiplier,
        profile.duration_floor_seconds,
    )
    enforce(script, script.budget_seconds)

    # 13. re-check the segment sizes, and say how long the finished programme actually is.
    _split_oversized(ctx, script)
    _retarget_transitions(ctx, script)
    _retime_orientation(ctx, script, prequestions, problem)

    # 14. the exposure log and the hand-off to part two (SPC-03).
    _repair_spacing(ctx, script)
    _record_exposures(script)
    script.schedule = _schedule_seeds(ctx, script, next_intervals)
    return script


#: Beat types that are the document being read out, rather than mimem talking about it.
_CONTENT_TYPES = frozenset(
    {
        BeatType.EXPOSITION,
        BeatType.TABLE,
        BeatType.FIGURE,
        BeatType.EQUATION,
        BeatType.ANSWER,
    }
)


def _straight_read_seconds(script: Script) -> float:
    """How long it would take to simply read the retained content aloud (rule DUR-02)."""
    return sum(beat.est_seconds for beat in script.beats() if beat.type in _CONTENT_TYPES)


# -- the body ------------------------------------------------------------------------------


def _section_groups(doc: Document) -> list[tuple[Block | None, list[Block]]]:
    """Retained blocks grouped by the heading that governs them.

    Front matter -- title, abstract -- has no heading above it, so it becomes a leading group
    with no source heading. Dropping it would drop the abstract, which is the densest part of a
    paper and the part rules ``STR-01`` and ``DIF-01`` lean on hardest.
    """
    groups: list[tuple[Block | None, list[Block]]] = []
    current: list[Block] = []
    heading: Block | None = None

    for block in retained(doc):
        if block.role is BlockRole.TITLE:
            continue  # spoken by the orientation beat instead (rule STR-01)
        if block.kind is BlockKind.HEADING:
            if current:
                groups.append((heading, current))
            heading, current = block, []
            continue
        current.append(block)
    if current:
        groups.append((heading, current))
    return _merge_fragments([(h, _place_figures(b)) for h, b in groups])


def _place_figures(blocks: list[Block]) -> list[Block]:
    """Rule FIG-04: a figure goes where the prose first mentions it, not where it sits.

    A figure's caption lands wherever the typesetter had room -- in the paper this was written
    against, between two and seventy-five blocks after the sentence that refers to it. On the
    page that is fine, because a reader's eye crosses the gap in an instant. In audio it means
    hearing about a figure a page and a half after the argument that needed it.

    Only within the section, and only forwards. Every referenced figure in the test paper is
    referred to from its own section and always *before* its caption, so a within-section move is
    the whole of the problem; a cross-section move would be relocating a claim into a part of
    the document that has not set it up yet.

    A figure nobody refers to stays where it is. That is one of eleven in the test paper, and
    reading order is the only answer available for it -- the fallback is worse than the rule,
    which is exactly why the rule needs one.
    """
    order = {block.id: i for i, block in enumerate(blocks)}
    moves: dict[str, str] = {}
    for block in blocks:
        meta = block.attrs.get("caption")
        if not isinstance(meta, dict):
            continue
        targets = [ref for ref in meta.get("references", []) if ref in order]
        if not targets:
            continue
        first = min(targets, key=lambda ref: order[ref])
        if order[first] < order[block.id]:
            moves[first] = block.id

    if not moves:
        return blocks
    moved = set(moves.values())
    out: list[Block] = []
    by_id = {block.id: block for block in blocks}
    for block in blocks:
        if block.id in moved:
            continue
        out.append(block)
        if block.id in moves:
            out.append(by_id[moves[block.id]])
    return out


def _merge_fragments(
    groups: list[tuple[Block | None, list[Block]]],
) -> list[tuple[Block | None, list[Block]]]:
    """Fold sections too short to stand on their own into the one above (see MIN_SECTION_WORDS)."""
    out: list[tuple[Block | None, list[Block]]] = []
    for heading, blocks in groups:
        words = sum(len(b.text.split()) for b in blocks)
        if words < MIN_SECTION_WORDS and out:
            previous_heading, previous_blocks = out[-1]
            out[-1] = (previous_heading, previous_blocks + blocks)
            continue
        out.append((heading, blocks))
    # A short *first* group has nothing above it, so it takes the next group with it.
    if len(out) > 1 and sum(len(b.text.split()) for b in out[0][1]) < MIN_SECTION_WORDS:
        heading, blocks = out[0]
        following_heading, following_blocks = out[1]
        out[:2] = [(heading or following_heading, blocks + following_blocks)]
    return out


def _section_id(heading: Block | None) -> str:
    return heading.id if heading is not None else "sec_front"


def _section_title(heading: Block | None, blocks: list[Block]) -> str:
    if heading is not None and heading.text.strip():
        return heading.text.strip()
    role = blocks[0].role if blocks else BlockRole.UNKNOWN
    return "The paper in brief" if role is BlockRole.ABSTRACT else "Opening"


def _card_pool(ctx: _Context, groups: list[tuple[Block | None, list[Block]]]) -> list[Card]:
    """One retrieval item per section, from that section's best-earning concept (rule RET-05).

    Per section rather than from the document's top concepts, because the review block
    interleaves *across* sections (rule STR-07): a pool drawn globally would come from two
    sections and have nothing to interleave with.

    A concept the section *introduces* is preferred over one it merely mentions. Rule ``STR-06``
    puts this question at the end of the section, so asking about something the listener met two
    sections ago produces a re-exposure the spacing scheduler did not choose and cannot move --
    and, on the first real build, one that landed two and a half minutes after the introduction
    against a three-minute minimum.
    """
    cards: list[Card] = []
    used: set[str] = set()
    # The source sentences already promised to a card. `SupportPool` tracks spending per
    # *concept*, so a sentence spent by one concept is still unspent for the next -- which
    # is right for exposition and wrong for cards, where it means two questions with one
    # answer (rule RET-06).
    spoken_answers: set[str] = set()
    first_mention = _first_mentions(ctx)
    order = {block.id: block.order for block in ctx.doc.blocks}
    for heading, blocks in groups:
        text = " ".join(b.text for b in blocks)
        block_ids = {b.id for b in blocks}
        mentioned = [
            c
            for c in ctx.registry.ranked()
            if ctx.patterns[c.id].search(text) and ctx.support.best(c.id) is not None
        ]
        eligible = [c for c in mentioned if c.id not in used]
        introduced_here = [c for c in eligible if first_mention.get(c.id) in block_ids]
        # A section that introduces nothing of its own still needs a closing question
        # (rule STR-06). Then the best one to ask is about whatever the listener met *longest*
        # ago: it is the only choice that improves the spacing rather than crowding it.
        fallback = sorted(eligible, key=lambda c: order.get(first_mention.get(c.id, ""), 10**6))
        concept = next(iter(introduced_here or fallback), None)

        support = _unshared_support(ctx, concept, spoken_answers) if concept else None
        if concept is None:
            # A paper with thirty sections runs out of unused concepts before it runs out of
            # sections. Asking about one twice is not a failure -- at this distance it is
            # spaced retrieval -- but it has to be a *different* sentence of the source, or the
            # second answer is the first one again (rule REP-01).
            concept, support = _reused_card_concept(ctx, mentioned)

        if concept is not None and support is not None:
            ctx.support.spend(support)
            used.add(concept.id)
            spoken_answers.add(support.spoken)
            cards.append(
                make.make_card(concept, support, _section_id(heading), ctx.profile, ctx.listener)
            )
            continue

        # No concept here at all -- a short section, or a document whose vocabulary never
        # repeats. The section still has a subject, and rule STR-06 still wants a question.
        topic = best_sentence(
            blocks,
            ctx.profile,
            ctx.listener,
            strip_superscripts=ctx.factory.strip_superscripts,
        )
        if topic is not None:
            cards.append(
                make.topic_card(
                    _section_title(heading, blocks),
                    topic,
                    _section_id(heading),
                    ctx.profile,
                    ctx.listener,
                )
            )
    return cards


def _reused_card_concept(
    ctx: _Context, mentioned: list[Concept]
) -> tuple[Concept | None, Support | None]:
    """The highest-scoring concept here that still has something unsaid about it."""
    for concept in mentioned:
        support = ctx.support.take(concept.id)
        if support is not None:
            return concept, support
    return None, None


def _first_mentions(ctx: _Context) -> dict[str, str]:
    """The first retained block that mentions each concept, in reading order.

    Deliberately *not* ``Concept.first_span``: that is where the extractor found the concept,
    which is often a definitional sentence somewhere in the middle. The listener meets a concept
    where the narration first says it, which is the first block in reading order -- and every
    rule about spacing and introduction is written about the listener.
    """
    out: dict[str, str] = {}
    for block in retained(ctx.doc):
        if block.kind is BlockKind.HEADING or not block.text.strip():
            continue
        for concept_id, pattern in ctx.patterns.items():
            if concept_id not in out and pattern.search(block.text):
                out[concept_id] = block.id
    return out


def _unshared_support(ctx: _Context, concept: Concept, taken: set[str]) -> Support | None:
    """The best sentence for this concept that no other card is already using (rule RET-06).

    ``SupportPool.best`` returns the strongest support "used or not", and its spending ledger is
    keyed per concept -- both correct for exposition, where one sentence can reasonably serve two
    ideas. For cards it is not: on the sensor paper it produced one sentence answering questions
    about "reference resonator", "resonant strain sensor" *and* "resonant strain". Three
    questions, one fact, and retrieval practice spent without being had.

    Falls back to the shared sentence rather than to nothing. A section with only one usable
    sentence should still get its question (``STR-06``); the duplicate is then reported by
    ``RET-06`` rather than silently costing the section its card.
    """
    options = ctx.support.by_concept.get(concept.id, [])
    definitional = [s for s in options if s.definitional]
    for candidate in (*definitional, *options):
        if candidate.spoken not in taken:
            return candidate
    return ctx.support.best(concept.id, definitional=True)


def _retarget_transitions(ctx: _Context, script: Script) -> None:
    """Withdraw any announcement the beats after it no longer keep (rule SEG-04).

    Transitions are chosen in ``_body``, and three later steps insert beats after them:
    ``_add_segment_prompts``, the budget's cutting pass, and ``_split_oversized``. A promise
    made before those ran can be false by the time a listener hears it -- "More on measurement
    resonator", then a question about resonant strain.

    Rather than move the transition or reorder the pipeline, the announcement is *withdrawn*:
    the beat falls back to naming the section, which is a smaller claim and always accurate.
    Saying less is the right way to stop being wrong.
    """
    beats = script.beats()
    window = ANNOUNCE_WINDOW
    for index, beat in enumerate(beats):
        if beat.type is not BeatType.TRANSITION or not beat.concept_ids:
            continue
        announced = set(beat.concept_ids)
        if any(
            announced & set(later.concept_ids) for later in beats[index + 1 : index + 1 + window]
        ):
            continue
        section = script.section_of(beat.id)
        title = section.title if section else ""
        beat.text = make.section_fallback_transition(ctx.factory, title)
        beat.concept_ids = []
        ctx.announced -= announced


def _prequestions(ctx: _Context, cards: list[Card]) -> list[Card]:
    """Rules STR-02 and PRQ-01: two to four, drawn from the card pool, never invented."""
    low, high = PREQUESTION_BOUNDS
    wanted = min(max(low, min(high, ctx.profile.prequestions_per_document)), len(cards))
    ranked = sorted(cards, key=lambda c: -_budget_of(ctx, c.concept_id))
    return ranked[:wanted]


def _budget_of(ctx: _Context, concept_id: str | None) -> float:
    concept = ctx.registry.concepts.get(concept_id or "")
    return concept.budget if concept else 0.0


def _body(
    ctx: _Context,
    groups: list[tuple[Block | None, list[Block]]],
    by_section: dict[str, Card],
    prequestion_ids: set[str],
) -> list[Section]:
    """Exposition, segmented, with position statements, recaps and one prompt per section."""
    sections: list[Section] = []
    total = len(groups)

    for index, (heading, blocks) in enumerate(groups, start=1):
        section_id = _section_id(heading)
        title = _section_title(heading, blocks)

        body: list[Beat] = []
        for block in blocks:
            for beat in make.exposition_beats(block, ctx.factory, ctx.patterns, skip=ctx.covered):
                body.append(beat)
                body.extend(_elaboration_beats(ctx, beat))
        if not body:
            continue

        section = Section(
            id=section_id,
            title=title,
            order=index,
            source_block_id=heading.id if heading else None,
        )
        opening = [make.position_beat(ctx.factory, title, index, total)]
        before = set(ctx.seen_concepts)
        section.segments = _segment(ctx, opening + body, section_id, title)
        introduced = {c for seg in section.segments for c in seg.concept_ids} - before
        _add_emphasis(ctx, section)
        _close_section(ctx, section, by_section.get(section_id), prequestion_ids, introduced)
        sections.append(section)
    return sections


def _elaboration_beats(ctx: _Context, beat: Beat) -> list[Beat]:
    """What stage 6 wrote about the concepts this beat introduces (rule DIF-02).

    Placed immediately after the sentence that first mentions the concept, and in the order the
    budget is spent: gloss, anchor, why, analogy. Explaining a term after showing its picture
    would be handing the listener an image of nothing.

    With no model configured the registry holds none of this and the function returns nothing,
    which is why ``--local`` produces exactly the M4 programme.
    """
    out: list[Beat] = []
    for concept_id in beat.concept_ids:
        concept = ctx.registry.concepts.get(concept_id)
        if concept is None or concept_id in ctx.elaborated:
            continue
        ctx.elaborated.add(concept_id)
        support = ctx.support.by_concept.get(concept_id, [])[:4]
        spans = [s.span for s in support]
        source = "\n".join(s.written for s in support)
        if not spans:
            continue

        if concept.long_def:
            out.append(make.gloss_beat(ctx.factory, concept, concept.long_def, spans, source))
        if concept.anchor is not None:
            out.append(make.anchor_beat(ctx.factory, concept, concept.anchor.text, source))
        if concept.why is not None:
            out.append(
                make.why_beat(
                    ctx.factory, concept, concept.why.text, concept.why.spans or spans, source
                )
            )
        if concept.analogy is not None:
            out.append(
                make.analogy_beat(
                    ctx.factory, concept, concept.analogy.text, concept.analogy.limit, source
                )
            )
    return out


def _segment(ctx: _Context, beats: list[Beat], section_id: str, title: str) -> list[Segment]:
    """Split a run of beats into duration-bounded segments (rules SEG-01, SEG-03).

    Two things force a break: the clock, and the new-term budget. The second is the reason the
    knowledge base gives for segmenting at all -- a segment boundary is a chance to consolidate,
    and a segment carrying five new terms has not given the listener one.
    """
    bounds = ctx.profile.segments
    limit = ctx.profile.max_new_terms_per_segment
    out: list[Segment] = []
    current: list[Beat] = []
    seconds = 0.0
    new_terms: set[str] = set()

    def flush() -> None:
        nonlocal current, seconds, new_terms
        if not current:
            return
        out.append(Segment(id=f"g_{section_id}_{len(out)}", section_id=section_id, beats=current))
        ctx.seen_concepts.update(new_terms)
        current, seconds, new_terms = [], 0.0, set()

    for beat in beats:
        taught = beat.concept_ids if beat.type in TEACHING_TYPES else []
        introduced = {c for c in taught if c not in ctx.seen_concepts} - new_terms
        over_time = bool(current) and (
            seconds + beat.total_seconds > bounds.hard_max
            or (seconds >= bounds.target_min and seconds + beat.total_seconds > bounds.target_max)
        )
        over_terms = bool(current) and len(new_terms | introduced) > limit
        if over_time or over_terms:
            flush()
            introduced = {c for c in taught if c not in ctx.seen_concepts}
        current.append(beat)
        seconds += beat.total_seconds
        new_terms |= introduced
    flush()

    for segment, following in pairwise(out):
        # Rule SEG-02: every boundary is audible. The last segment of a section ends on the
        # recap and the section-boundary pause instead.
        concept, is_new = _next_concept(ctx, following)
        segment.beats.append(make.transition_beat(ctx.factory, concept, title, is_new=is_new))
    return out


#: How many beats into the next segment an announcement may look. A transition promises what
#: comes *next*; a concept three beats in is not next.
ANNOUNCE_WINDOW = 3


def _opening_concepts(segment: Segment) -> list[str]:
    """The concepts the next few beats are actually about, in order.

    ``segment.concept_ids`` is every concept anywhere in the segment, and announcing from that
    set produced transitions that were simply untrue: "More on measurement resonator" followed
    immediately by a question about resonant strain, four times in one programme. The concept
    was in the segment; it was not what came next. Rule ``SEG-04`` now checks the promise, and
    this is what keeps it.
    """
    seen: dict[str, None] = {}
    for beat in segment.beats[:ANNOUNCE_WINDOW]:
        for concept_id in beat.concept_ids:
            seen.setdefault(concept_id, None)
    return list(seen)


def _next_concept(ctx: _Context, segment: Segment) -> tuple[Concept | None, bool]:
    """What a transition should announce, and whether it is new to the listener.

    Never the same concept two boundaries running: "more on gradient boosting" three times in a
    row is the template talking, and rule ``VOI-03`` exists to keep that out of the audio.

    Only concepts the *opening* of the next segment is about, so that the announcement is true
    when the listener hears what follows it (rule ``SEG-04``). Announcing nothing is better than
    announcing wrongly: ``transition_beat`` falls back to naming the section, which is a smaller
    claim and always accurate.
    """
    known: Concept | None = None
    for concept_id in _opening_concepts(segment):
        concept = ctx.registry.concepts.get(concept_id)
        if concept is None or concept_id in ctx.announced:
            continue
        if concept_id not in ctx.seen_concepts:
            ctx.announced.add(concept_id)
            return concept, True
        if known is None or concept.budget > known.budget:
            known = concept
    if known is not None:
        ctx.announced.add(known.id)
    return known, False


def _add_emphasis(ctx: _Context, section: Section) -> None:
    """Rule SIG-02: mark the core claim, at most once per section, so the marker keeps force."""
    if ctx.profile.emphasis_markers_per_section < 1:
        return
    best: tuple[float, Segment, int, Concept] | None = None
    for segment in section.segments:
        for i, beat in enumerate(segment.beats):
            if beat.type is not BeatType.EXPOSITION:
                continue
            for concept_id in beat.concept_ids:
                concept = ctx.registry.concepts.get(concept_id)
                if concept is None:
                    continue
                if best is None or concept.importance > best[0]:
                    best = (concept.importance, segment, i, concept)
    if best is None:
        return
    _, segment, index, concept = best
    segment.beats.insert(index, make.emphasis_beat(ctx.factory, concept))


def _close_section(
    ctx: _Context,
    section: Section,
    card: Card | None,
    prequestion_ids: set[str],
    introduced: set[str],
) -> None:
    """Rule STR-06: a micro-recap and one retrieval prompt, at the end of every section."""
    if not section.segments:
        return
    last = section.segments[-1]
    present: dict[str, Concept] = {}
    for segment in section.segments:
        for concept_id in segment.concept_ids:
            concept = ctx.registry.concepts.get(concept_id)
            if concept is not None:
                present.setdefault(concept_id, concept)
    # Only what this section *added*. A section that introduced nothing new gets the short
    # form: listing concepts it merely mentioned again produced the previous section's recap
    # with a different heading in front of it, eight times over.
    fresh = sorted((c for cid, c in present.items() if cid in introduced), key=lambda c: -c.budget)
    last.beats.append(make.recap_beat(ctx.factory, fresh, section.title))

    if card is not None:
        last.beats.extend(make.prompt_beats(ctx.factory, card))
        if card.id in prequestion_ids:
            last.beats.append(make.prequestion_close_beat(ctx.factory, card))
    last.beats[-1].pause_after = max(
        last.beats[-1].pause_after, ctx.profile.pauses.section_boundary
    )


def _add_segment_prompts(ctx: _Context, script: Script) -> None:
    """Rule RET-03: up to one retrieval prompt per segment, where there is one to ask.

    Only about a concept the segment itself taught, and only from a sentence the listener has
    not already been given as an answer -- otherwise the "question" is a sentence they heard
    ninety seconds ago, which tests recognition rather than recall.

    Stops at the duration budget. Prompts are protected from the budget cuts (``DUR-02``), so
    adding one is a commitment; the check belongs here rather than in a later pass that would
    have to break its own rule to undo it.
    """
    allowed = ctx.profile.prompts_per_segment
    if allowed < 1:
        return
    budget = script.budget_seconds
    running = script.est_seconds

    for section in script.sections:
        for segment in section.segments:
            if segment.has(BeatType.PROMPT) or running >= budget:
                continue
            placed = 0
            for concept_id in _taught_in(segment):
                if placed >= allowed:
                    break
                concept = ctx.registry.concepts.get(concept_id)
                if concept is None:
                    continue
                support = ctx.support.take(concept_id)
                if support is None:
                    continue
                card = make.make_card(
                    concept, support, segment.section_id, ctx.profile, ctx.listener
                )
                beats = make.prompt_beats(ctx.factory, card)
                cost = sum(b.total_seconds for b in beats)
                if running + cost > budget:
                    ctx.support.spend(support)
                    break
                script.cards.append(card)
                segment.beats.extend(beats)
                running += cost
                placed += 1


def _taught_in(segment: Segment) -> list[str]:
    """Concepts this segment actually teaches, in the order it teaches them."""
    out: dict[str, None] = {}
    for beat in segment.beats:
        if beat.type in TEACHING_TYPES:
            for concept_id in beat.concept_ids:
                out.setdefault(concept_id, None)
    return list(out)


# -- the opening ---------------------------------------------------------------------------


def _orientation(
    ctx: _Context, script: Script, prequestions: list[Card], problem: Support | None
) -> Beat:
    """Rule STR-01, including how long the whole thing takes."""
    promises = [
        ctx.registry.concepts[c.concept_id]
        for c in prequestions
        if c.concept_id is not None and c.concept_id in ctx.registry.concepts
    ]
    return make.orientation_beat(
        ctx.factory,
        ctx.doc.source.title or "this paper",
        ctx.doc.source.authors,
        script.est_seconds / 60.0,
        problem,
        promises or ctx.registry.ranked(3),
    )


def _retime_orientation(
    ctx: _Context, script: Script, prequestions: list[Card], problem: Support | None
) -> None:
    """Rebuild the orientation once the programme's real length is known.

    The orientation has to exist before the spacing scheduler runs, because the callbacks are
    placed on a clock that starts after it -- but the callbacks, the review block and the
    segment prompts are all still to come at that point, so the duration it announces is the
    duration of a programme that is not the one being shipped. Telling the listener five minutes
    for an eight-minute programme is a small lie and an easy one to avoid.
    """
    if not script.opening or script.opening[0].type is not BeatType.ORIENTATION:
        return
    script.opening[0] = _orientation(ctx, script, prequestions, problem)


def _opening(
    ctx: _Context, script: Script, prequestions: list[Card], problem: Support | None
) -> list[Beat]:
    """Rules STR-01, STR-02, STR-03: orientation, prequestions, term pre-load."""
    out = [_orientation(ctx, script, prequestions, problem)]
    out.extend(make.prequestion_beats(ctx.factory, prequestions))

    terms: list[tuple[Concept, str]] = []
    for concept in preload_terms(ctx.registry, ctx.profile.max_preload_terms):
        gloss = concept.short_def
        if not gloss:
            support = ctx.support.best(concept.id, definitional=True)
            gloss = support.spoken if support is not None and support.definitional else None
        if gloss:
            terms.append((concept, gloss))
    out.extend(make.preload_beats(ctx.factory, terms))
    return out


def _problem_sentence(ctx: _Context) -> Support | None:
    """The paper's own framing sentence, for "why anyone cared" (rule STR-01).

    Taken from the abstract, and then *excluded* from the exposition: saying the same sentence
    twice inside a minute is the verbatim repetition rule ``REP-01`` forbids, and a listener
    hears it as a stutter rather than as emphasis.
    """
    for block in retained(ctx.doc):
        if block.role is not BlockRole.ABSTRACT or block.kind is BlockKind.HEADING:
            continue
        for start, end in block.sentences or [(0, len(block.text))]:
            sentence = block.text[start:end].strip()
            if len(sentence.split()) < 8:
                continue
            spoken = ctx.factory.speak(sentence)
            if not spoken:
                continue
            ctx.covered.add((block.id, start, end))
            return Support(
                concept_id="",
                spoken=spoken,
                written=sentence,
                span=Span(block_id=block.id, char_start=start, char_end=end, page=block.page),
                section_id=block.section_id,
                score=1.0,
            )
    return None


# -- spacing -------------------------------------------------------------------------------


def _place_callbacks(ctx: _Context, script: Script) -> dict[str, float]:
    """Rules SPC-01, SPC-02, REP-02: bring each concept back at increasing intervals.

    Slots are segment boundaries only. The review block is already a guaranteed final exposure
    for every card concept, so offering it as a slot would double up at the end and starve the
    middle of the document -- which is the only place a callback changes anything.

    Returns the interval each concept was heading towards, for the part-two hand-off.
    """
    first_seen: dict[str, tuple[float, str]] = {}
    slots: list[Slot] = []
    at = sum(b.total_seconds for b in script.opening)

    for section in script.sections:
        for segment in section.segments:
            for beat in segment.beats:
                if beat.type is BeatType.EXPOSITION:
                    for concept_id in beat.concept_ids:
                        first_seen.setdefault(concept_id, (at, segment.section_id))
                at += beat.total_seconds
            slots.append(Slot(id=segment.id, at_seconds=at, section_id=segment.section_id))

    requests = [
        Request(
            concept_id=concept_id,
            first_at=first_at,
            repetitions=repetitions_for(
                ctx.registry.concepts[concept_id].difficulty,
                ctx.registry.concepts[concept_id].importance,
                ctx.profile.spacing,
            ),
            home_section_id=section_id,
            priority=ctx.registry.concepts[concept_id].budget,
        )
        for concept_id, (first_at, section_id) in first_seen.items()
        if concept_id in ctx.registry.concepts
    ]
    result = schedule(requests, slots, ctx.profile.spacing)

    by_segment: dict[str, list[str]] = {}
    for placement in result.placements:
        by_segment.setdefault(placement.slot_id, []).append(placement.concept_id)
    exhausted: dict[str, int] = {}
    for section in script.sections:
        for segment in section.segments:
            for concept_id in by_segment.get(segment.id, []):
                callback = make.callback_beat(
                    ctx.factory,
                    ctx.registry.concepts[concept_id],
                    ctx.support.take(concept_id),
                )
                if callback is None:
                    exhausted[concept_id] = exhausted.get(concept_id, 0) + 1
                    continue
                segment.beats.append(callback)

    for concept_id, missed in exhausted.items():
        result.unplaced[concept_id] = result.unplaced.get(concept_id, 0) + missed
    script.notes.extend(
        f"{ctx.registry.concepts[cid].canonical}: the source had nothing further to say, "
        f"so {n} scheduled exposure(s) were left out"
        for cid, n in sorted(exhausted.items())
        if cid in ctx.registry.concepts
    )

    script.notes.extend(
        f"{ctx.registry.concepts[cid].canonical}: {n} exposure(s) did not fit the document"
        for cid, n in sorted(result.unplaced.items())
        if cid in ctx.registry.concepts
    )
    return result.next_interval_minutes


def _split_oversized(ctx: _Context, script: Script) -> None:
    """Split any segment that ended up over the hard maximum (rule SEG-01).

    The closing recap and prompt, the emphasis marker and the spaced callbacks are all appended
    *after* segmentation, so a segment sized at ninety seconds can ship at a hundred and
    twenty-five. Splitting here rather than reserving room earlier keeps the reserve from being
    a guess: at this point the beats are known.

    A prompt is never separated from its answer -- that would trade one rule violation for a
    worse one (``RET-01``) -- and the new boundary gets its transition, because a boundary the
    listener cannot hear is not a boundary (``SEG-02``).
    """
    bounds = ctx.profile.segments
    for section in script.sections:
        out: list[Segment] = []
        for segment in section.segments:
            out.extend(_split(ctx, segment, section.title, bounds.hard_max, bounds.target_max))
        section.segments = out


def _split(
    ctx: _Context, segment: Segment, title: str, hard_max: float, target_max: float
) -> list[Segment]:
    if segment.est_seconds <= hard_max or len(segment.beats) < 2:
        return [segment]

    cut = _cut_point(segment, target_max)
    if cut is None:
        return [segment]

    head = Segment(
        id=segment.id,
        section_id=segment.section_id,
        beats=[*segment.beats[:cut], make.transition_beat(ctx.factory, None, title, is_new=False)],
    )
    tail = Segment(id=f"{segment.id}x", section_id=segment.section_id, beats=segment.beats[cut:])
    return [head, *_split(ctx, tail, title, hard_max, target_max)]


def _cut_point(segment: Segment, target_max: float) -> int | None:
    """The last beat boundary that keeps the first part under the target, or ``None``."""
    running = 0.0
    best: int | None = None
    for i, beat in enumerate(segment.beats):
        running += beat.total_seconds
        following = segment.beats[i + 1] if i + 1 < len(segment.beats) else None
        if following is None:
            break
        if beat.type is BeatType.PROMPT or following.type is BeatType.ANSWER:
            continue  # rule RET-01: a prompt and its answer are one unit
        if running <= target_max:
            best = i + 1
    return best


def _repair_spacing(ctx: _Context, script: Script) -> None:
    """Drop any callback the final timeline puts too close to its neighbour (rule SPC-01).

    Inserting callbacks and then cutting beats to fit the budget both move the clock, so the
    schedule the scheduler proved correct is not automatically the schedule that ships. This is
    the pass that makes the invariant hold of the artefact rather than of the intention.
    """
    min_gap = ctx.profile.spacing.min_gap_minutes * 60.0
    for _ in range(MAX_REPAIR_PASSES):
        offenders = _too_close(script, min_gap)
        if not offenders:
            return
        for beat_id in offenders:
            _remove_beat(script, beat_id, "SPC-01", "closer than the minimum gap to the previous")
    script.notes.append("spacing repair gave up; see the SPC-01 violations in the lint report")


def _too_close(script: Script, min_gap: float) -> set[str]:
    """Callback beats whose exposure lands inside the minimum gap."""
    offenders: set[str] = set()
    for entries in exposure_log(script).values():
        episodes = spaced(entries, min_gap)
        for previous, current in pairwise(episodes):
            if current.at_seconds - previous.at_seconds < min_gap and current.form == (
                ExposureForm.CALLBACK.value
            ):
                offenders.add(current.beat_id)
    return offenders


def _remove_beat(script: Script, beat_id: str, rule: str, reason: str) -> None:
    for section in script.sections:
        for segment in section.segments:
            target = next((b for b in segment.beats if b.id == beat_id), None)
            if target is None:
                continue
            segment.beats = [b for b in segment.beats if b.id != beat_id]
            script.dropped.append(
                DropRecord(
                    beat_id=target.id,
                    beat_type=target.type,
                    rule=rule,
                    reason=reason,
                    est_seconds=target.total_seconds,
                    text=target.text,
                )
            )
            return


# -- review, exposures, schedule ---------------------------------------------------------------


def _review(ctx: _Context, cards: list[Card]) -> list[Beat]:
    """Rule STR-07: the closing review, interleaved across sections."""
    if not cards:
        return []
    ordered, collisions = interleave(cards)
    out = [make.review_lead_beat(ctx.factory, len(ordered))]
    for card in ordered:
        out.extend(make.prompt_beats(ctx.factory, card, review=True))
    if collisions:
        out[0].attrs["interleave_collisions"] = collisions
    return out


def _record_exposures(script: Script) -> None:
    """Rule SPC-03: every exposure, on the concept, in the artefact."""
    log = exposure_log(script)
    for concept_id, concept in script.registry.items():
        concept.exposures = [
            Exposure(beat_id=e.beat_id, at_seconds=round(e.at_seconds, 1), form=e.form)
            for e in log.get(concept_id, [])
        ]


def _schedule_seeds(
    ctx: _Context, script: Script, next_intervals: dict[str, float]
) -> list[ScheduledReview]:
    """What part two needs to carry on scheduling after the programme ends (rule SPC-03)."""
    default = ctx.profile.spacing.min_gap_minutes * ctx.profile.spacing.interval_ratio
    out: list[ScheduledReview] = []
    for concept_id, concept in script.registry.items():
        met = [e for e in concept.exposures if e.form in COUNTED_FORMS]
        if not met:
            continue
        wanted = repetitions_for(concept.difficulty, concept.importance, ctx.profile.spacing)
        out.append(
            ScheduledReview(
                concept_id=concept_id,
                exposures=len(met),
                last_at_seconds=round(max(e.at_seconds for e in met), 1),
                next_interval_minutes=next_intervals.get(concept_id, default),
                unplaced=max(0, wanted - len(met)),
            )
        )
    return sorted(out, key=lambda s: (-s.exposures, s.concept_id))
