"""Layer 1 of the evaluation: what can be measured on every build, for free.

The design rules are arguments from the literature. The linter turns each argument into a
pass/fail. Neither of them tells you whether the programme got *better* between two commits, and
that is the question this module answers -- not by judging quality, which needs people, but by
measuring the handful of quantities the design is actually a claim about.

Each metric is here because a specific way of getting worse would show up in it and in nothing
else:

``spacing``      A planner that quietly stops finding slots reports the same lint result and a
                 different interval distribution. ``SPC-01`` asks whether any gap is too small;
                 this asks whether the gaps are still growing, which is the finding.
``gloss``        Term coverage falls silently when the concept scorer drifts. Nothing fails.
``grounding``    The fraction of beats that can point at a page. ``GRD-01`` fails a build at
                 zero coverage of a *type*; this notices the slow leak.
``numbers``      Values reaching the written track. A verbalizer change that starts eating
                 units would pass ``NUM-02``, which only asks that no digits are spoken.
``retention``    How much of the document survived triage. A greedy new drop rule shows up here
                 first, and the drop report is 400 lines long.
``duration``     Estimated against budget. *Not* prediction error: there is no measured audio
                 until M7, so the honest quantity is how close the planner ran to its own
                 allowance, and the real one waits for a speech engine to disagree with.

Everything is a ratio in ``0..1`` or a plain count, so a baseline can be compared without
knowing what any of it means -- see :mod:`mimem.eval.harness`.
"""

from __future__ import annotations

import re
import statistics
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from mimem.config import Profile
from mimem.ir import GENERATED_TYPES, BeatType, Document, ExposureForm, Script
from mimem.lint import LintReport
from mimem.plan.exposure import LoggedExposure, exposure_log, spaced

#: A value worth checking survived: it has a decimal part, a unit, or enough digits that speech
#: had to chunk it. Shared with rule ``NUM-06``, which asks the same question as a pass/fail.
VALUE = re.compile(r"\d+\.\d+|\d{4,}|\d+(?:\.\d+)?\s*(?:%|°|µ|nm|mm|cm|km|kg|mg|mA|mAh|V|W|Hz|K)\b")


class Metrics(BaseModel):
    """One build, measured. Every field is a ratio in 0..1 or a count."""

    model_config = ConfigDict(extra="forbid")

    document: str = ""

    # -- lint -------------------------------------------------------------------------------
    lint_errors: int = 0
    lint_warnings: int = 0
    rules_checked: int = 0
    rules_skipped: int = 0

    # -- shape ------------------------------------------------------------------------------
    minutes: float = 0.0
    budget_minutes: float = 0.0
    #: 1.0 means the programme used exactly its allowance. Over 1.0 means it overran.
    budget_used: float = 0.0
    sections: int = 0
    segments: int = 0
    beats: int = 0
    cards: int = 0

    # -- the design's own claims ------------------------------------------------------------
    #: Concepts that got a one-line definition before they were used (rules STR-03, SEG-03).
    gloss_coverage: float = 0.0
    #: Concepts met more than once (rule SPC-02). The spacing effect is the largest in the
    #: literature and the one audio is worst at, so this is the headline number.
    concepts_spaced: float = 0.0
    #: Of the concepts that recur, how many have non-decreasing intervals (rule SPC-02).
    intervals_expanding: float = 0.0
    #: The denominator of ``intervals_expanding``: how many concepts it averages over.
    recurring_concepts: int = 0
    median_gap_minutes: float = 0.0
    #: Beats that can point at a page, of those required to (rule GRD-01).
    grounded: float = 0.0
    #: Source values that reached the written track (rule NUM-06).
    values_kept: float = 0.0
    #: Words of the source that survived triage (rule COH-01..05).
    words_retained: float = 0.0
    #: Prompts per minute of programme. Retrieval practice is the second-largest effect.
    prompts_per_minute: float = 0.0

    def compare(self, other: Metrics, tolerance: float = 0.02) -> list[str]:
        """Every way ``self`` is worse than ``other`` by more than ``tolerance``.

        Direction matters and differs per field, which is why this is a method and not a
        dictionary diff: more lint errors is worse, more spaced concepts is better, and
        ``budget_used`` is worse in *either* direction past the allowance.
        """
        out: list[str] = []
        for name in ("lint_errors", "rules_skipped"):
            mine, theirs = getattr(self, name), getattr(other, name)
            if mine > theirs:
                out.append(f"{name}: {theirs} -> {mine}")
        if self.rules_checked < other.rules_checked:
            out.append(f"rules_checked: {other.rules_checked} -> {self.rules_checked}")
        for name in (
            "gloss_coverage",
            "concepts_spaced",
            "intervals_expanding",
            "grounded",
            "values_kept",
            "words_retained",
            "prompts_per_minute",
        ):
            mine, theirs = getattr(self, name), getattr(other, name)
            if mine < theirs - tolerance:
                out.append(f"{name}: {theirs:.3f} -> {mine:.3f}")
        if self.budget_used > max(1.0, other.budget_used) + tolerance:
            out.append(f"budget_used: {other.budget_used:.3f} -> {self.budget_used:.3f}")
        return out


def measure(
    doc: Document,
    script: Script,
    report: LintReport,
    study: str,
    profile: Profile,
    name: str = "",
) -> Metrics:
    """Measure one build."""
    minutes = script.est_seconds / 60.0
    budget = script.budget_seconds / 60.0
    prompts = sum(1 for b in script.beats() if b.type is BeatType.PROMPT)
    episodes = _episodes(script, profile)
    gaps = _gaps(episodes)

    return Metrics(
        document=name or doc.source.title or doc.id,
        lint_errors=len(report.errors),
        lint_warnings=len(report.warnings),
        rules_checked=len(set(report.checked_rules)),
        rules_skipped=len(report.skipped),
        minutes=round(minutes, 2),
        budget_minutes=round(budget, 2),
        budget_used=round(minutes / budget, 3) if budget else 0.0,
        sections=len(script.sections),
        segments=len(script.segments()),
        beats=len(script.beats()),
        cards=len(script.cards),
        gloss_coverage=_gloss_coverage(script, episodes),
        concepts_spaced=_concepts_spaced(episodes),
        intervals_expanding=_intervals_expanding(episodes),
        recurring_concepts=_recurring_concepts(episodes),
        median_gap_minutes=round(statistics.median(gaps) / 60.0, 2) if gaps else 0.0,
        grounded=_grounded(script),
        values_kept=_values_kept(script, study),
        words_retained=_words_retained(doc),
        prompts_per_minute=round(prompts / minutes, 3) if minutes else 0.0,
    )


# -- the individual measurements -------------------------------------------------------------


def _episodes(script: Script, profile: Profile) -> dict[str, list[LoggedExposure]]:
    """When each concept was met, in the same terms rule ``SPC-01`` uses.

    Recomputed from the beats via :func:`exposure_log`, and coalesced with the profile's own
    minimum gap, so the number here and the pass/fail there are answers to one question. A
    metric that measured spacing differently from the rule enforcing it would eventually
    disagree with it, and there would be no way to tell which one was wrong.
    """
    min_gap = profile.spacing.min_gap_minutes * 60.0
    return {
        concept_id: spaced(entries, min_gap) for concept_id, entries in exposure_log(script).items()
    }


def _gloss_coverage(script: Script, episodes: dict[str, list[LoggedExposure]]) -> float:
    met = [script.registry[cid] for cid in episodes if cid in script.registry]
    if not met:
        return 0.0
    return round(sum(1 for c in met if c.short_def) / len(met), 3)


def _concepts_spaced(episodes: dict[str, list[LoggedExposure]]) -> float:
    if not episodes:
        return 0.0
    return round(sum(1 for times in episodes.values() if len(times) > 1) / len(episodes), 3)


def _intervals_expanding(episodes: dict[str, list[LoggedExposure]]) -> float:
    """Of the concepts the scheduler placed three times or more, how many never shrink (SPC-02).

    Shrinking intervals are not a small deviation from expanding ones: they are massed practice
    with extra steps, and massed practice is what the whole design is a reaction to.

    The tolerance is 10%. The scheduler places exposures at real beat boundaries, not at ideal
    times, so an interval can come back a little short without the schedule having stopped
    expanding -- and a metric that called that a regression would fire on every document.

    **Only shrinks that close on a callback count.** This is the same distinction rule
    ``SPC-01``'s linter has always made, and it took a false regression to notice the metric was
    not making it. A callback exists because the spacing scheduler put it there, so a short gap
    before one is a scheduling failure. An introduction and the prompt that closes its section
    are placed by ``STR-04`` and ``STR-06``; in a paper whose sections run two minutes they
    cannot be three minutes apart, and no scheduler can make them so. Counting those measured
    the length of the document's sections and reported it as the spacing system failing.
    """
    recurring = [entries for entries in episodes.values() if len(entries) > 2]
    if not recurring:
        return 1.0  # nothing to get wrong; not evidence of anything, but not a regression
    good = 0
    for entries in recurring:
        intervals = [(b.at_seconds - a.at_seconds, b.form) for a, b in pairwise(entries)]
        if all(
            b >= a * 0.9 or form != ExposureForm.CALLBACK.value
            for (a, _), (b, form) in pairwise(intervals)
        ):
            good += 1
    return round(good / len(recurring), 3)


def _recurring_concepts(episodes: dict[str, list[LoggedExposure]]) -> int:
    """How many concepts ``intervals_expanding`` is actually an average over.

    A fraction computed from one concept can move from 1.0 to 0.0 because a single concept
    dropped from three exposures to two, which is what happened the first time the corpus
    changed underneath it. Recording the denominator puts that in the diff instead of leaving a
    reviewer to infer it from a number that looks like a collapse.
    """
    return sum(1 for entries in episodes.values() if len(entries) > 2)


def _gaps(episodes: dict[str, list[LoggedExposure]]) -> list[float]:
    out: list[float] = []
    for times in episodes.values():
        out.extend(b.at_seconds - a.at_seconds for a, b in pairwise(times))
    return out


def _grounded(script: Script) -> float:
    """Rule GRD-01, as a fraction rather than a pass/fail."""
    owed = [b for b in script.beats() if b.type not in GENERATED_TYPES and b.text.strip()]
    if not owed:
        return 1.0
    return round(sum(1 for b in owed if b.spans) / len(owed), 3)


def _values_kept(script: Script, study: str) -> float:
    """Rule NUM-06, as a fraction: source values that reached the written track."""
    values: set[str] = set()
    for beat in script.beats():
        if beat.written_text:
            values |= {m.group(0).strip() for m in VALUE.finditer(beat.written_text)}
    if not values:
        return 1.0
    return round(sum(1 for v in values if v in study) / len(values), 3)


def _words_retained(doc: Document) -> float:
    from mimem.triage.rules import retained

    total = doc.word_count
    if not total:
        return 0.0
    return round(sum(len(b.text.split()) for b in retained(doc)) / total, 3)


class Corpus(BaseModel):
    """Metrics for a set of documents, which is what a baseline is."""

    model_config = ConfigDict(extra="forbid")

    documents: list[Metrics] = Field(default_factory=list)

    def compare(self, other: Corpus, tolerance: float = 0.02) -> dict[str, list[str]]:
        """Every regression against ``other``, keyed by document.

        A document present here and missing there is not a regression -- adding a paper to the
        corpus is how the corpus grows. A document missing *here* is: it means the harness
        stopped being able to build something it used to build, which is the loudest possible
        signal and the easiest to lose in a diff.
        """
        mine = {m.document: m for m in self.documents}
        out: dict[str, list[str]] = {}
        for name, theirs in ((m.document, m) for m in other.documents):
            if name not in mine:
                out[name] = ["no longer builds"]
                continue
            diff = mine[name].compare(theirs, tolerance)
            if diff:
                out[name] = diff
        return out
