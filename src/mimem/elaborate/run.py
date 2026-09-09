"""Running the elaboration tasks, and surviving them failing.

Three commitments, and they are the reason this is a separate module from the transport.

**Every task has a degradation path, and it is taken silently only in the sense that the
listener is not interrupted -- the manifest always says what happened.** One unreachable figure
must not kill a three-hundred-page book, so a failure here is a smaller programme, never a
failed build.

**Nothing generated is trusted because it is fluent.** A gloss and a why-explanation are claims
about the document, so they pass the deterministic grounding checks (``GRD-03``) against the
sentences they were written from before they are stored. A number the source does not state is a
rejection, not a warning.

**An anchor and an analogy are ours and are checked differently.** They are *supposed* to
contain things the paper never said -- that is what an image for an abstract idea is -- so
checking them for invented names would reject every good one. What they may not do is invent a
*number*, because a number in an anchor reads as a fact. So they get the numeric check only, and
rule ``VOI-02`` makes the planner introduce them as ours when they are spoken.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mimem.config import Listener, Profile
from mimem.elaborate.reconcile import Absence, Deterministic, Mode, classify
from mimem.elaborate.sentences import LongSentence, over_long, verify_split
from mimem.ir import (
    Analogy,
    Anchor,
    Block,
    Concept,
    ConceptRegistry,
    Document,
    Elaboration,
    Span,
)
from mimem.llm import tasks
from mimem.llm.cache import CacheStats
from mimem.llm.client import Client, LLMRefusedError, LLMUnavailableError, NullClient, Request
from mimem.llm.cost import BudgetExceededError, Ledger, Plan, estimate
from mimem.llm.schemas import AnalogyOut, AnchorOut, FigureOut, GlossOut, SplitOut, WhyOut

# The supporting-sentence index is shared between stage 6 and stage 7. It lives with the
# planner, which is its heavier user; importing it here is deliberate rather than a layering
# accident, because both stages must agree on what the source says about a concept.
from mimem.plan.support import Support, SupportPool, gather
from mimem.verify import Severity, check
from mimem.verify.grounding import Finding

#: How much of the source to put in the cached prefix. A whole book does not fit and does not
#: need to: the task carries the sentences that matter, and the document is context.
MAX_DOCUMENT_CHARS = 60_000

#: The cap the split is asked to get under, and it is *below* the linter's thirty-five. A
#: sentence that lands exactly on the limit written is over it spoken, because the numbers in it
#: have not been said yet -- see :func:`~mimem.elaborate.sentences.over_long`. Asking for
#: twenty-five leaves room for the verbalizer.
SPLIT_CAP = 25

#: Every task that can be reconciled, so a mode exists for each.
TASKS = ("gloss", "anchor", "analogy", "why", "figure", "compress", "split")


@dataclass(frozen=True)
class Degradation:
    """A task that did not produce usable output, and what happened instead."""

    task: str
    concept: str
    reason: str
    fallback: str
    #: *Why* there is no model answer. Four different situations were one string until M9, and
    #: they need four different actions from the user -- see :class:`Absence`.
    kind: Absence = Absence.UNREACHABLE

    def __str__(self) -> str:
        return f"{self.task} for {self.concept!r}: [{self.kind.value}] {self.reason} -> {self.fallback}"


@dataclass
class ElaborationReport:
    """What stage 6 did. Goes into ``manifest.json`` more or less verbatim."""

    attempted: dict[str, int] = field(default_factory=dict)
    succeeded: dict[str, int] = field(default_factory=dict)
    #: Tasks answered by the deterministic implementation. Counted separately from ``succeeded``
    #: so that "what did the model actually add" is a number rather than an impression.
    deterministic: dict[str, int] = field(default_factory=dict)
    degraded: list[Degradation] = field(default_factory=list)
    rejected: list[Finding] = field(default_factory=list)
    ledger: Ledger = field(default_factory=Ledger)
    cache: CacheStats | None = None
    #: True when no provider was configured, so nothing was attempted rather than failing
    #: once per task. Reported once, which is the useful number of times.
    no_provider: bool = False

    def _count(self, bucket: dict[str, int], task: str) -> None:
        bucket[task] = bucket.get(task, 0) + 1

    def summary(self) -> str:
        if self.no_provider:
            got = sum(self.deterministic.values())
            return (
                f"no model configured; {got} written from the source's own sentences "
                "(`mimem doctor` says what this machine can reach)"
            )
        if not self.attempted:
            return "no elaboration attempted"
        done = ", ".join(f"{n} {task}" for task, n in sorted(self.succeeded.items())) or "nothing"
        out = f"wrote {done}"
        if self.deterministic:
            total = sum(self.deterministic.values())
            out += f"; {total} from the source's own sentences"
        if self.degraded:
            out += f"; {len(self.degraded)} degraded"
        if self.rejected:
            out += f"; {len(self.rejected)} rejected by the grounding check"
        return out

    def absences(self) -> dict[Absence, int]:
        """How many tasks each kind of absence accounts for.

        The distinction the manifest could not previously make. "Everything degraded" means
        something very different when it is one missing key than when it is forty rejected
        claims, and only one of those is a problem with the setup.
        """
        counts: dict[Absence, int] = {}
        for entry in self.degraded:
            counts[entry.kind] = counts.get(entry.kind, 0) + 1
        return counts


def _document_text(doc: Document) -> str:
    from mimem.triage.rules import retained

    return "\n\n".join(b.text for b in retained(doc))[:MAX_DOCUMENT_CHARS]


def _support_texts(pool: SupportPool, concept_id: str, limit: int = 6) -> list[str]:
    return [s.written for s in pool.by_concept.get(concept_id, [])[:limit]]


def _spans(pool: SupportPool, concept_id: str, limit: int = 6) -> list[Span]:
    return [s.span for s in pool.by_concept.get(concept_id, [])[:limit]]


def _anchor_targets(candidates: list[Concept], profile: Profile) -> set[str]:
    """Rule IMG-01: abstract *and* important. Either alone is not enough.

    An abstract aside does not earn a picture, and a concrete central idea already has one.
    Importance enters as rank -- the candidates are already ordered by ``difficulty x
    importance`` -- because an absolute cut on a within-document score selects nothing on a real
    paper: see the note on :class:`~mimem.config.ElaborationBudget`.
    """
    floor = profile.elaboration.anchor_min_abstractness
    abstract = [c for c in candidates if c.signals.get("abstractness", 0.0) >= floor]
    return {c.id for c in abstract[: profile.elaboration.max_anchors]}


def _candidates(registry: ConceptRegistry, profile: Profile) -> list[Concept]:
    """Concepts worth spending on, hardest and most central first (rule DIF-02)."""
    ranked = [c for c in registry.ranked() if c.budget > 0]
    return ranked[: profile.elaboration.max_concepts]


def plan_requests(
    doc: Document,
    registry: ConceptRegistry,
    profile: Profile,
    listener: Listener | None = None,
    model: str | None = None,
) -> Plan:
    """Every call this run would make, without making any of them (the ``--dry-run`` report).

    ``model`` is what the estimate is priced against, and it was missing. ``--dry-run --model``
    quoted the default model's price whatever you asked for, so the one question a dry run
    exists to answer -- *what will the cheap model save me?* -- returned the same number for
    Opus, Sonnet and Haiku. On a 98-page review that was $2.48 three times over for prices that
    differ by nearly twenty-fold.
    """
    plan = Plan()
    for request in _requests(doc, registry, profile, listener):
        plan.add(replace(request, model=model) if model else request)
    return plan


def _requests(
    doc: Document,
    registry: ConceptRegistry,
    profile: Profile,
    listener: Listener | None,
) -> Iterator[Request]:
    """The requests, in the order rule DIF-02 spends the budget."""
    document = _document_text(doc)
    pool = gather(doc, dict(registry.concepts), profile, listener)
    candidates = _candidates(registry, profile)
    anchors = _anchor_targets(candidates, profile)
    for concept in candidates:
        support = _support_texts(pool, concept.id)
        if not support:
            continue
        if not concept.short_def:
            yield tasks.gloss(concept, support, document, listener)
        if concept.id in anchors and concept.anchor is None:
            yield tasks.anchor(concept, support, document, listener)
        if concept.why is None:
            yield tasks.why(concept, support, document)
    for concept in _candidates(registry, profile)[: profile.elaboration.max_analogies]:
        if concept.analogy is None and _support_texts(pool, concept.id):
            yield tasks.analogy(concept, _support_texts(pool, concept.id), document, listener)

    # Figures, so that --dry-run prices them. The image is not available here -- crops are
    # rendered into the output directory, which a dry run does not have -- so the estimate
    # falls back to DEFAULT_IMAGE_TOKENS, which is deliberately generous rather than optimistic.
    from mimem.elaborate.figures import figure_tasks

    for task in figure_tasks(doc):
        yield tasks.figure(task.caption, task.references, document)

    # Sentence splits, which are the one task whose count scales with the length of the paper
    # rather than with the number of concepts -- so a dry run that did not price them was
    # quoting for the wrong build on anything longer than a letter.
    for sentence in over_long(doc, profile, listener)[: profile.elaboration.max_splits]:
        yield tasks.split(sentence.text, document, SPLIT_CAP)


def elaborate(
    doc: Document,
    registry: ConceptRegistry,
    profile: Profile,
    listener: Listener | None = None,
    client: Client | None = None,
    *,
    budget: float | None = None,
    out_dir: Path | None = None,
    model: str | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> ElaborationReport:
    """Fill in the glosses, anchors, why-explanations and analogies the budget allows.

    Mutates ``registry``. With :class:`NullClient` -- the default -- nothing is written and every
    task is recorded as degraded, which is exactly what ``--local`` mode should produce: a
    complete, honest report of what was not done.

    ``model`` is stamped onto every request, and it has to be, because ``Request.model`` carries
    ``DEFAULT_MODEL`` and ``AnthropicClient`` resolves ``request.model or self.model`` -- a
    default that is always truthy, so the client's own model was never reached. ``--model``
    was accepted, ignored, and billed at the default's price: one real run asked for Haiku,
    was answered by Opus, and cost $0.79 instead of about a tenth of that. The estimate is
    priced from ``request.model`` too, so stamping here is also what makes the ledger true.

    ``progress`` is called before each request as ``(task, subject)``. Stage 6 is the only part
    of a build that is slow *and* silent -- twenty-six calls with no output looks exactly like a
    hang, which is how it was first reported.
    """
    client = client or NullClient()
    report = ElaborationReport(ledger=Ledger(cap=budget))

    # With no provider at all, every task is `off` rather than "attempt, fail, fall back". The
    # old behaviour produced one degradation per task saying the same thing forty times, which
    # is how "you have no API key" came to look like forty separate problems. One line says it.
    if isinstance(client, NullClient):
        report.no_provider = True
        modes = dict.fromkeys(TASKS, Mode.OFF)
    else:
        modes = {task: Mode(profile.elaboration.mode_for(task)) for task in TASKS}
    document = _document_text(doc)
    pool = gather(doc, dict(registry.concepts), profile, listener)
    candidates = _candidates(registry, profile)
    anchors = _anchor_targets(candidates, profile)

    for concept in candidates:
        support = _support_texts(pool, concept.id)
        if not support:
            continue
        spans = _spans(pool, concept.id)
        source = "\n".join(support)

        if not concept.short_def:
            _run(
                report,
                client,
                tasks.gloss(concept, support, document, listener),
                concept.canonical,
                partial(_apply_gloss, concept),
                source=source,
                fallback="the source's own definitional sentence",
                model=model,
                progress=progress,
                mode=modes["gloss"],
                on_degrade=partial(_definition_from_the_source, concept, pool),
            )
        if concept.id in anchors and concept.anchor is None:
            _run(
                report,
                client,
                tasks.anchor(concept, support, document, listener),
                concept.canonical,
                partial(_apply_anchor, concept),
                source=source,
                kinds=GROUNDING_KINDS["anchor"],
                fallback="no anchor",
                model=model,
                progress=progress,
                mode=modes["anchor"],
            )
        if concept.why is None:
            _run(
                report,
                client,
                tasks.why(concept, support, document),
                concept.canonical,
                partial(_apply_why, concept, spans),
                source=source,
                fallback="no why-explanation",
                model=model,
                progress=progress,
                mode=modes["why"],
            )

    for concept in candidates[: profile.elaboration.max_analogies]:
        support = _support_texts(pool, concept.id)
        if not support or concept.analogy is not None:
            continue
        _run(
            report,
            client,
            tasks.analogy(concept, support, document, listener),
            concept.canonical,
            partial(_apply_analogy, concept),
            source="\n".join(support),
            kinds=GROUNDING_KINDS["analogy"],
            fallback="no analogy",
            model=model,
            progress=progress,
            mode=modes["analogy"],
        )

    _describe_figures(report, client, doc, document, out_dir, model=model, progress=progress)
    _split_sentences(
        report,
        client,
        doc,
        document,
        profile,
        listener,
        mode=modes["split"],
        model=model,
        progress=progress,
    )
    return report


def _split_sentences(
    report: ElaborationReport,
    client: Client,
    doc: Document,
    document: str,
    profile: Profile,
    listener: Listener | None,
    *,
    mode: Mode,
    model: str | None,
    progress: Callable[[str, str], None] | None,
) -> None:
    """Cut the sentences a listener cannot hold in one piece (rule SENT-01).

    Last, and deliberately. Every other task competes for the elaboration budget against the
    *concepts* rule DIF-02 ranks; this one competes against the length of the paper, and a
    hundred splits would starve the four analogies that carry the programme. Running it after
    the others means the budget answers the question in the right order.
    """
    if mode is Mode.OFF:
        return
    for sentence in over_long(doc, profile, listener)[: profile.elaboration.max_splits]:
        block = doc.block(sentence.block_id)
        _run(
            report,
            client,
            tasks.split(sentence.text, document, SPLIT_CAP),
            _shorten(sentence.text),
            partial(_apply_split, block, sentence),
            source=sentence.text,
            inspect=lambda data, source: verify_split(source, list(data.sentences), cap=SPLIT_CAP),
            fallback="the source sentence, unchanged",
            model=model,
            progress=progress,
            mode=mode,
        )


def _shorten(text: str, words: int = 6) -> str:
    """A sentence named by its opening, for the progress line and the degradation report."""
    head = text.split()[:words]
    return " ".join(head) + ("..." if len(text.split()) > words else "")


def _apply_split(block: Block, sentence: LongSentence, out: SplitOut) -> None:
    """Store the split beside the sentence it replaces, leaving the source alone."""
    block.rewrites[sentence.key] = " ".join(s.strip() for s in out.sentences)


def _describe_figures(
    report: ElaborationReport,
    client: Client,
    doc: Document,
    document: str,
    out_dir: Path | None,
    *,
    model: str | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> None:
    """Say what each figure shows, when there is a crop to look at (PLAN-figures stage C).

    Skipped entirely without ``out_dir``: describing a figure from its caption alone is the
    thing the confidence field exists to refuse, and a task that can only degrade is better not
    attempted than attempted and reported.

    A figure has no concept, so this does not go through :func:`_run` -- but it keeps the same
    three commitments: budget checked before spending, output checked before storing, and a
    failure recorded as a degradation rather than raised.
    """
    from mimem.elaborate import figures as fig

    if out_dir is None:
        return
    for task in fig.figure_tasks(doc):
        image = fig.image_bytes(task, out_dir)
        if image is None:
            continue
        request = tasks.figure(task.caption, task.references, document, image)
        if model:
            request = replace(request, model=model)
        if progress is not None:
            progress("figure", task.label or "a figure")
        report._count(report.attempted, "figure")
        label = f"figure {task.number}" if task.number else "a figure"
        try:
            report.ledger.check(estimate(request))
            response = client.complete(request)
        except BudgetExceededError:
            raise
        except (LLMUnavailableError, LLMRefusedError) as exc:
            report.degraded.append(Degradation("figure", label, str(exc), "the caption alone"))
            continue

        report.ledger.record(response)
        out = response.data
        if not isinstance(out, FigureOut):  # pragma: no cover - the schema guarantees this
            continue
        ok, findings = fig.accept(out, task.source)
        if not ok:
            report.rejected.extend(findings)
            reason = (
                "; ".join(str(f) for f in findings[:3])
                if findings
                else f"confidence {out.confidence:.2f} below {fig.MIN_CONFIDENCE}"
            )
            report.degraded.append(Degradation("figure", label, reason, "the caption alone"))
            continue

        fig.store(doc.block(task.block_id), out)
        report._count(report.succeeded, "figure")


def _run(
    report: ElaborationReport,
    client: Client,
    request: Request,
    subject: str,
    apply: Callable[[Any], None],
    *,
    source: str,
    fallback: str,
    kinds: tuple[str, ...] = ("number", "year", "name", "direction"),
    inspect: Callable[[Any, str], list[Finding]] | None = None,
    on_degrade: Deterministic | None = None,
    mode: Mode = Mode.PREFER,
    model: str | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> None:
    """One task: its two implementations, its budget, its grounding check, and who wins.

    ``on_degrade`` is the deterministic implementation. It was named for when it ran -- after a
    failure -- and under ``assist`` it runs *first*, which is the whole point of the mode: the
    rules answer what they are good at, and the model is asked only about the rest. It returns
    whether it produced anything, because nothing else can tell the caller that.

    ``inspect`` replaces the grounding check for a task whose contract is different. Everything
    here writes *new* text and can only be asked whether it invented something; a sentence split
    is lossless, so it is also asked whether it lost something, which no other task can fail.

    ``subject`` is a name for the thing being worked on, for the progress line and the
    degradation report. It was a whole :class:`Concept` until the split arrived, which has none.
    """
    deterministic = on_degrade

    if mode is Mode.OFF:
        if deterministic is not None and deterministic():
            report._count(report.deterministic, request.task)
        return

    if mode is Mode.ASSIST and deterministic is not None and deterministic():
        # The rules answered. Calling the model now would cost a request to produce something
        # that would be discarded, which is a real cost for no gain -- `mimem compare` is the
        # place that measures the two against each other.
        report._count(report.deterministic, request.task)
        return

    if model:
        request = replace(request, model=model)
    if progress is not None:
        progress(request.task, subject)

    report._count(report.attempted, request.task)
    try:
        report.ledger.check(estimate(request))
        response = client.complete(request)
    except BudgetExceededError:
        raise
    except (LLMUnavailableError, LLMRefusedError) as exc:
        _degrade(report, request.task, subject, str(exc), fallback, classify(exc))
        if deterministic is not None and deterministic():
            report._count(report.deterministic, request.task)
        return

    report.ledger.record(response)
    findings = (
        inspect(response.data, source)
        if inspect is not None
        else ground(response.data, source, kinds=kinds)
    )
    if findings:
        report.rejected.extend(findings)
        _degrade(
            report,
            request.task,
            subject,
            "; ".join(str(f) for f in findings[:3]),
            fallback,
            Absence.REJECTED,
        )
        if deterministic is not None and deterministic():
            report._count(report.deterministic, request.task)
        return

    apply(response.data)
    report._count(report.succeeded, request.task)


def _degrade(
    report: ElaborationReport,
    task: str,
    concept: str,
    reason: str,
    fallback: str,
    kind: Absence,
) -> None:
    report.degraded.append(Degradation(task, concept, reason, fallback, kind))


#: Which checks each task's output faces (rule GRD-03). A gloss or a why-explanation is a claim
#: *about the document*, so it faces all of them. An anchor and an analogy are ours and are
#: supposed to contain what the paper never said, so they face the numeric checks only -- see the
#: module docstring.
GROUNDING_KINDS: dict[str, tuple[str, ...]] = {
    "gloss": ("number", "year", "name", "direction"),
    "why": ("number", "year", "name", "direction"),
    "anchor": ("number", "year"),
    "analogy": ("number", "year"),
    "compress": ("number", "year", "name", "direction"),
    # A figure description is a claim *about the document*, so it faces the direction checks
    # too -- "capacity falls" where the paper says it rises is the failure this exists for. It
    # is excused the name check for the reason an anchor is: the legend names species the
    # running text often never mentions.
    "figure": ("number", "year", "direction"),
}


def store(
    concept: Concept,
    task: str,
    data: BaseModel,
    spans: list[Span] | None = None,
) -> None:
    """Put a checked elaboration on a concept.

    Public for the same reason :func:`ground` is: the assistant round trip in
    :mod:`mimem.assistant` writes to the registry too, and two functions that both know how a
    gloss is stored will eventually disagree about it.

    Call :func:`ground` first. This does not check anything.
    """
    if isinstance(data, GlossOut):
        _apply_gloss(concept, data)
    elif isinstance(data, AnchorOut):
        _apply_anchor(concept, data)
    elif isinstance(data, AnalogyOut):
        _apply_analogy(concept, data)
    elif isinstance(data, WhyOut):
        _apply_why(concept, spans or [], data)
    else:
        raise ValueError(f"nothing knows how to store the output of {task!r}")


def ground(
    data: BaseModel,
    source: str,
    *,
    kinds: tuple[str, ...] = ("number", "year", "name", "direction"),
) -> list[Finding]:
    """The gate: what in this generated output the cited source does not support (rule GRD-03).

    Public, and called by every path that accepts generated text -- the API client in this
    module and the assistant round trip in :mod:`mimem.assistant`. "The same check runs whatever
    wrote it" is a claim worth making only while it is one function rather than two that happen
    to agree.

    Returns the *blocking* findings. Warnings (an unfamiliar proper noun, say) are informative
    rather than disqualifying and are deliberately not returned here.
    """
    return [
        f
        for f in check(_claim_text(data), source)
        if f.kind in kinds and f.severity is Severity.ERROR
    ]


#: Fields that carry no claim, and so are not checked against the source. ``spoken`` is a
#: pronunciation; ``evidence`` and ``note`` are the verifier talking *about* a claim rather than
#: making one.
_NOT_A_CLAIM = frozenset({"spoken", "evidence", "note"})


def _claim_text(data: BaseModel) -> str:
    """Everything in a task's output that asserts something, for the grounding check.

    The fallback reads every string field rather than looking for one called ``text``, and that
    is the whole point of it. The old fallback returned ``getattr(data, "text", "")``, so a
    schema without a ``text`` field was checked against the empty string and passed — silently,
    and reported as "accepted". ``FigureOut`` has six fields and none of them is called ``text``,
    which meant the grounding gate did not cover figure descriptions at all: the output with the
    highest hallucination risk in the system was the one output nothing was checking.

    A description of a pie chart claiming hydrogen "climbs from 12.4 percent to 51.8 percent",
    with both numbers invented, passed cleanly. Now it does not.

    So an unknown schema now fails *closed*: every string it carries is treated as a claim.
    Over-checking costs a false positive that somebody reads; under-checking costs a fabricated
    number nobody hears about.
    """
    if isinstance(data, GlossOut):
        return f"{data.short_def} {data.long_def}"
    if isinstance(data, AnchorOut):
        return data.text
    if isinstance(data, AnalogyOut):
        return f"{data.text} {data.limit}"
    if isinstance(data, WhyOut):
        return data.text
    return " ".join(
        value
        for name, value in data
        if name not in _NOT_A_CLAIM and isinstance(value, str) and value
    )


# -- applying the results ----------------------------------------------------------------------


def _apply_gloss(concept: Concept, out: GlossOut) -> None:
    concept.short_def = out.short_def
    concept.long_def = out.long_def
    if out.spoken:
        concept.spoken = out.spoken


def _apply_anchor(concept: Concept, out: AnchorOut) -> None:
    concept.anchor = Anchor(text=out.text, generated_by="llm", verified=True)


def _apply_analogy(concept: Concept, out: AnalogyOut) -> None:
    concept.analogy = Analogy(text=out.text, limit=out.limit, generated_by="llm", verified=True)


def _apply_why(concept: Concept, spans: list[Span], out: WhyOut) -> None:
    concept.why = Elaboration(text=out.text, spans=spans, generated_by="llm", verified=True)


def _definition_from_the_source(concept: Concept, pool: SupportPool) -> bool:
    """The paper's own definitional sentence, for rule PRE-01's pre-load line.

    Returns whether the concept ends up with a definition, which is what ``assist`` needs to
    decide whether the model has anything left to do. It is ``True`` when the concept already
    had one -- from :mod:`mimem.concepts.definitions`, before this stage ran -- because the
    question the caller is asking is "is this task answered", not "did I answer it".
    """
    if concept.short_def:
        return True
    support: Support | None = pool.best(concept.id, definitional=True)
    if support is not None and support.definitional:
        concept.short_def = support.written
        return True
    return False
