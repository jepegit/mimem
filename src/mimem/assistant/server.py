"""The MCP server: mimem, driven from a conversation.

Nine tools and three prompts, named for what a person wants rather than for the pipeline stage
that does it. Nobody asking an assistant to explain a paper should have to know that stage 4
exists.

Three things shape every tool here.

**Context is the scarce resource.** A hundred-minute programme is fifteen thousand words, and a
tool that returned ``audio.md`` would fill the conversation and leave no room for the
conversation. Everything returns a summary; text comes one section at a time, capped, and the cap
is written into the tool description so the assistant can plan around it.

**Stdout belongs to the protocol.** This module never prints. A stray ``print`` on an MCP stdio
server corrupts the stream and presents as an unexplained disconnection, which is why this has
its own entry point rather than reusing the ``typer`` CLI and its console.

**The grounding gate does not care who wrote the text.** :func:`apply_elaborations` runs exactly
the same check as the API path -- one function, in :mod:`mimem.elaborate` -- so an assistant
writing a gloss is subject to the same rejection as a model behind an API key. That is the whole
reason it is safe to let the conversation do stage 6.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import ImageContent
from pydantic import BaseModel, Field

from mimem import __version__
from mimem.assistant import review as review_module
from mimem.assistant.workspace import SourceError, Workspace, build
from mimem.config import Listener, Profile, Settings, load_listener, load_profile
from mimem.elaborate import GROUNDING_KINDS, ground, store
from mimem.elaborate.figures import MIN_CONFIDENCE as MIN_FIGURE_CONFIDENCE
from mimem.ir import Concept, ConceptRegistry, Document, Script
from mimem.llm.schemas import AnalogyOut, AnchorOut, FigureOut, GlossOut, WhyOut
from mimem.llm.tasks import SYSTEM, analogy, anchor, gloss, why
from mimem.pipeline import replan
from mimem.plan.support import gather

#: Hard cap on the text any one tool returns. Roughly two thousand words: enough to read a
#: section aloud, small enough that a dozen calls do not exhaust a conversation.
MAX_TEXT_CHARS = 12_000

#: How many elaboration tasks to hand over at once. The assistant writes better in small batches,
#: and a rejected batch is cheaper to redo.
MAX_TASKS_PER_CALL = 6

#: What each task is allowed to return.
TASK_SCHEMAS: dict[str, type[BaseModel]] = {
    "gloss": GlossOut,
    "anchor": AnchorOut,
    "analogy": AnalogyOut,
    "why": WhyOut,
    "figure": FigureOut,
}

#: Tasks that belong to a figure rather than to a concept, and are answered with a ``figure_id``.
FIGURE_TASKS = frozenset({"figure"})


def instruction_for(task: str, concept: Concept, support: list[str], listener: Listener) -> str:
    """The instruction the assistant is given for a task.

    Deliberately the *same* text the API path sends: switching between an API key and the
    conversation changes who writes, not what is asked for. Written as a dispatch rather than a
    table of builders because `why` takes no listener -- it is asking about the document, not
    about the reader.
    """
    if task == "gloss":
        return gloss(concept, support, "", listener).instruction.strip()
    if task == "anchor":
        return anchor(concept, support, "", listener).instruction.strip()
    if task == "analogy":
        return analogy(concept, support, "", listener).instruction.strip()
    if task == "why":
        return why(concept, support, "").instruction.strip()
    raise ValueError(f"unknown task {task!r}")


mcp = MCPServer(
    name="mimem",
    title="mimem",
    version=__version__,
    instructions=(
        "mimem turns a paper into audio designed to be remembered rather than merely read "
        "aloud: an orientation, questions to hold on to, terms explained before they are used, "
        "the paper in short segments each ending on a question, and the key ideas brought back "
        "at growing intervals.\n\n"
        "Typical flow: build_programme, then elaboration_plan and apply_elaborations to write "
        "the explanations and concrete images yourself, then read_programme to walk through it, "
        "then study_session and grade_card on later days.\n\n"
        "Tools return summaries, never whole documents. Ask for one section at a time.\n\n"
        "Anything you write in apply_elaborations is checked against the paper's own sentences "
        "before it is stored: a number the paper does not state is rejected. Write from the "
        "source sentences you are given, and say you do not know rather than filling a gap."
    ),
)


def _settings() -> Settings:
    return Settings()


def _profile(name: str | None) -> Profile:
    try:
        return load_profile(name or "study", _settings())
    except FileNotFoundError as exc:
        raise ValueError(str(exc)) from exc


def _listener(path: str | None) -> Listener:
    return load_listener(Path(path).expanduser() if path else None, _settings())


def _workspace() -> Workspace:
    return Workspace.open()


def _script(workspace: Workspace, programme_id: str) -> Script:
    path = workspace.directory(programme_id) / "script.json"
    if not path.exists():
        raise ValueError(f"programme {programme_id!r} has no script.json")
    return Script.from_json(path.read_bytes())


def _registry(workspace: Workspace, programme_id: str) -> ConceptRegistry:
    return ConceptRegistry.from_json(
        (workspace.directory(programme_id) / "registry.json").read_bytes()
    )


def _clip(text: str, limit: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    cut = text.rfind("\n\n", 0, limit)
    return text[: cut if cut > limit // 2 else limit], True


# -- building ------------------------------------------------------------------------------------


@mcp.tool(
    title="Build a programme",
    description=(
        "Turn a paper into a listenable programme. Give exactly one of: `path` (a file on this "
        "machine), `url` (fetched over http or https), or `text` (the document itself, at least "
        "400 characters). Returns a summary — the duration, the structure, the top concepts and "
        "the lint verdict — never the text. Takes a few seconds for a long PDF."
    ),
)
def build_programme(
    path: Annotated[str | None, Field(description="A PDF, EPUB, Markdown or text file")] = None,
    url: Annotated[str | None, Field(description="An http(s) link to fetch")] = None,
    text: Annotated[str | None, Field(description="The document's text, pasted")] = None,
    profile: Annotated[str, Field(description="skim, study or drill")] = "study",
    listener_file: Annotated[str | None, Field(description="Path to a listener.yaml")] = None,
    name: Annotated[str | None, Field(description="A short name for the programme")] = None,
) -> dict[str, Any]:
    workspace = _workspace()
    try:
        result, record = build(
            workspace,
            _profile(profile),
            _listener(listener_file),
            path=path,
            url=url,
            text=text,
            name=name,
        )
    except SourceError as exc:
        raise ValueError(str(exc)) from exc

    top = [
        {"concept": c.canonical, "difficulty": round(c.difficulty, 2)}
        for c in result.registry.ranked(6)
    ]
    return {
        **record,
        "top_concepts": top,
        "directory": str(result.out_dir),
        "audio_file": str(result.out_dir / "audio.md"),
        "next": (
            "Call elaboration_plan to write the explanations and concrete images yourself, or "
            "read_programme to walk through what is there."
        ),
    }


@mcp.tool(
    title="List programmes",
    description="Every programme built in this workspace, newest first.",
)
def list_programmes() -> dict[str, Any]:
    workspace = _workspace()
    items = workspace.list()
    return {
        "workspace": str(workspace.root),
        "count": len(items),
        "programmes": [
            {
                key: item.get(key)
                for key in ("id", "title", "minutes", "cards", "built_at", "profile")
            }
            for item in items[:40]
        ],
    }


@mcp.tool(
    title="Read a programme",
    description=(
        "Read part of a programme. `part` is 'outline' (default — the structure and where "
        "everything is), 'audio' (what a speech engine would say) or 'study' (the written "
        "companion, with page numbers and exact figures). Audio and study are returned one "
        f"section at a time; give `section` as the index from the outline. Capped at "
        f"{MAX_TEXT_CHARS} characters per call."
    ),
)
def read_programme(
    programme_id: str,
    part: Annotated[str, Field(description="outline, audio or study")] = "outline",
    section: Annotated[int | None, Field(description="Section index from the outline")] = None,
) -> dict[str, Any]:
    workspace = _workspace()
    directory = workspace.directory(programme_id)
    script = _script(workspace, programme_id)

    if part == "outline":
        return {
            "programme_id": programme_id,
            "title": script.source.title,
            "minutes": round(script.est_seconds / 60, 1),
            "opening": [b.type.value for b in script.opening],
            "sections": [
                {
                    "index": i,
                    "title": s.title,
                    "minutes": round(s.est_seconds / 60, 1),
                    "segments": len(s.segments),
                    "questions": sum(1 for b in s.beats() if b.type.value == "prompt"),
                }
                for i, s in enumerate(script.sections)
            ],
            "review_questions": sum(1 for b in script.review if b.type.value == "prompt"),
        }

    if part not in {"audio", "study"}:
        raise ValueError("part must be 'outline', 'audio' or 'study'")

    if section is None:
        body = (directory / f"{part}.md").read_text(encoding="utf-8")
        text, truncated = _clip(body)
        return {
            "programme_id": programme_id,
            "part": part,
            "text": text,
            "truncated": truncated,
            "hint": "Pass `section` to read one section at a time." if truncated else "",
        }

    if not 0 <= section < len(script.sections):
        raise ValueError(f"section must be between 0 and {len(script.sections) - 1}")

    chosen = script.sections[section]
    beats = chosen.beats()
    body = "\n\n".join(
        (b.written_text or b.text) if part == "study" else b.text for b in beats if b.text.strip()
    )
    text, truncated = _clip(body)
    return {
        "programme_id": programme_id,
        "part": part,
        "section": section,
        "section_title": chosen.title,
        "text": text,
        "truncated": truncated,
        "sections_total": len(script.sections),
    }


# -- the elaboration round trip ---------------------------------------------------------------


@mcp.tool(
    title="Plan the elaborations",
    description=(
        "The explanations mimem wants written for this programme, with the paper's own sentences "
        "to write them from. You write the answers and pass them to apply_elaborations. "
        "Everything you write is checked against those sentences before it is stored — a number "
        "the paper does not state is rejected — so write only from what you are given."
    ),
)
def elaboration_plan(
    programme_id: str,
    limit: Annotated[int, Field(description=f"At most {MAX_TASKS_PER_CALL}", ge=1)] = 4,
    profile: str = "study",
) -> dict[str, Any]:
    workspace = _workspace()
    directory = workspace.directory(programme_id)
    registry = _registry(workspace, programme_id)
    settings = load_profile(profile, _settings())
    listener = _listener(None)

    doc = Document.from_json((directory / "doc.ir.json").read_bytes())
    pool = gather(doc, dict(registry.concepts), settings, listener)

    tasks: list[dict[str, Any]] = []
    for concept in registry.ranked(settings.elaboration.max_concepts):
        support = [s.written for s in pool.by_concept.get(concept.id, [])[:5]]
        if not support:
            continue
        wanted = []
        if not concept.long_def:
            wanted.append("gloss")
        if concept.why is None:
            wanted.append("why")
        if concept.anchor is None and concept.signals.get("abstractness", 0) >= 0.5:
            wanted.append("anchor")
        for task in wanted:
            if len(tasks) >= min(limit, MAX_TASKS_PER_CALL):
                break
            schema = TASK_SCHEMAS[task].model_json_schema()
            tasks.append(
                {
                    "task": task,
                    "concept_id": concept.id,
                    "concept": concept.canonical,
                    "difficulty": round(concept.difficulty, 2),
                    "importance": round(concept.importance, 2),
                    "source_sentences": support,
                    "instruction": instruction_for(task, concept, support, listener),
                    "fields": sorted(schema.get("properties", {})),
                    "required": schema.get("required", []),
                }
            )
        if len(tasks) >= min(limit, MAX_TASKS_PER_CALL):
            break

    return {
        "programme_id": programme_id,
        "house_style": SYSTEM.strip(),
        "tasks": tasks,
        "remaining_after_this": max(0, len(registry.concepts) - len(tasks)),
        "next": (
            "Write each task's fields and send them to apply_elaborations as "
            '[{"task": ..., "concept_id": ..., "fields": {...}}].'
            if tasks
            else "Nothing left to elaborate."
        ),
    }


@mcp.tool(
    title="Show me a figure to describe",
    description=(
        "Returns one figure from a programme as an image, with its caption and the sentences "
        "that refer to it, for you to describe. Send the description back to apply_elaborations "
        'as {"task": "figure", "figure_id": ..., "fields": {...}}. Call again for the '
        "next one. Describe only what you can see; do not state a value the paper's own text "
        "does not, because the check will reject it and it should."
    ),
)
def next_figure(
    programme_id: str,
    figure_id: Annotated[
        str | None, Field(description="A specific figure, or the next one")
    ] = None,
) -> list[Any]:
    """Hand the assistant a figure to look at.

    A tool of its own rather than part of ``elaboration_plan`` for two reasons. A figure belongs
    to a *place in the document* rather than to a concept, so it is answered with a ``figure_id``
    and nothing about it fits the concept-shaped plan. And it returns an image, which means the
    result is a list of content blocks rather than one JSON object.

    One at a time on purpose. Each crop crosses the transport as base64, and a description is
    worth more attention than a batch of six invites.
    """
    from mimem.elaborate.figures import described, figure_tasks

    workspace = _workspace()
    directory = workspace.directory(programme_id)
    doc = Document.from_json((directory / "doc.ir.json").read_bytes())

    pending = [
        task
        for task in figure_tasks(doc)
        if task.image
        and task.image is not None
        and (directory / task.image).exists()
        and described(doc.block(task.block_id)) is None
        and (figure_id is None or task.block_id == figure_id)
    ]
    if not pending:
        return [
            {
                "programme_id": programme_id,
                "remaining": 0,
                "note": "Every figure with a crop has been described.",
            }
        ]

    task = pending[0]
    schema = FigureOut.model_json_schema()
    return [
        {
            "programme_id": programme_id,
            "figure_id": task.block_id,
            "number": task.number,
            "caption": task.caption,
            "source_sentences": task.references,
            "fields": sorted(schema.get("properties", {})),
            "remaining": len(pending),
            "instruction": (
                "Describe this figure for someone who cannot see it, in the order the fields "
                "ask for: a title-like statement under 125 characters, then what kind of figure "
                "it is, then the axes and units, then the trend, then any notable exceptions, "
                "then the claim it supports. Never speak the figure's number. Mention colour "
                "only if colour carries meaning.\n\n"
                "Do not state a value that the caption or the sentences above do not state. "
                "Numbers you read off the plot cannot be checked against anything, so they are "
                "rejected whether they are right or wrong -- say 'well over half' instead. Set "
                "confidence honestly: below "
                f"{MIN_FIGURE_CONFIDENCE} the description is discarded and the caption is used."
            ),
        },
        _image_content((directory / str(task.image)).read_bytes()),
    ]


def _apply_figure(
    doc: Document, answer: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any] | None:
    """Validate, check and store one figure description. ``None`` means it was accepted."""
    from mimem.elaborate import figures as fig

    figure_id = str(answer.get("figure_id", ""))
    try:
        block = doc.block(figure_id)
    except KeyError:
        return {"task": "figure", "figure_id": figure_id, "reason": "no such figure"}

    try:
        data = FigureOut.model_validate(fields)
    except Exception as exc:
        return {"task": "figure", "figure_id": figure_id, "reason": f"schema: {exc}"}

    task = next((t for t in fig.figure_tasks(doc) if t.block_id == figure_id), None)
    source = task.source if task is not None else block.text
    ok, findings = fig.accept(data, source)
    if not ok:
        return {
            "task": "figure",
            "figure_id": figure_id,
            "reason": (
                "; ".join(str(f) for f in findings[:3])
                if findings
                else f"confidence {data.confidence:.2f} is below {fig.MIN_CONFIDENCE}"
            ),
            "advice": (
                "A value you read off the plot cannot be checked against anything, so it is "
                "rejected whether it is right or wrong. Say 'well over half' rather than a "
                "percentage, unless the paper's own text states the number."
            ),
        }

    fig.store(block, data)
    return None


def _image_content(png: bytes) -> ImageContent:
    # ``mime_type`` in this SDK version, not ``mimeType``. The wire format is camelCase and the
    # Python attribute is not, which has now cost time twice in this repository.
    return ImageContent(
        type="image",
        data=base64.b64encode(png).decode("ascii"),
        mime_type="image/png",
    )


@mcp.tool(
    title="Apply the elaborations",
    description=(
        "Store the explanations you wrote. Each answer is {task, concept_id, fields}. Every one "
        "is validated against its schema and then checked against the paper's own sentences; "
        "anything stating a number or reversing a direction the paper does not is rejected and "
        "reported back. Re-plans the programme afterwards so the new material is in the audio."
    ),
)
def apply_elaborations(
    programme_id: str,
    answers: list[dict[str, Any]],
    profile: str = "study",
) -> dict[str, Any]:
    workspace = _workspace()
    directory = workspace.directory(programme_id)
    registry = _registry(workspace, programme_id)
    settings = load_profile(profile, _settings())
    listener = _listener(None)

    doc = Document.from_json((directory / "doc.ir.json").read_bytes())
    pool = gather(doc, dict(registry.concepts), settings, listener)

    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []

    figures_stored = 0

    for answer in answers:
        task = str(answer.get("task", ""))
        concept_id = str(answer.get("concept_id", ""))
        fields = answer.get("fields") or {}

        if task in FIGURE_TASKS:
            outcome = _apply_figure(doc, answer, fields)
            if outcome is None:
                figures_stored += 1
                accepted.append(f"figure: {answer.get('figure_id', '')}")
            else:
                rejected.append(outcome)
            continue

        concept = registry.concepts.get(concept_id)
        if task not in TASK_SCHEMAS or concept is None:
            rejected.append(
                {"task": task, "concept_id": concept_id, "reason": "unknown task or concept"}
            )
            continue

        try:
            data = TASK_SCHEMAS[task].model_validate(fields)
        except Exception as exc:
            rejected.append(
                {"task": task, "concept": concept.canonical, "reason": f"schema: {exc}"}
            )
            continue

        support = [s.written for s in pool.by_concept.get(concept_id, [])[:6]]
        findings = ground(data, "\n".join(support), kinds=GROUNDING_KINDS[task])
        if findings:
            rejected.append(
                {
                    "task": task,
                    "concept": concept.canonical,
                    "reason": "; ".join(str(f) for f in findings[:3]),
                    "advice": "Rewrite it using only what the source sentences say.",
                }
            )
            continue

        spans = [s.span for s in pool.by_concept.get(concept_id, [])[:4]]
        store(concept, task, data, spans)
        accepted.append(f"{task}: {concept.canonical}")

    (directory / "registry.json").write_text(registry.to_json(), encoding="utf-8")
    if figures_stored:
        # A figure description lives on its caption block, so the document is what changed and
        # the document is what `replan` will read back.
        (directory / "doc.ir.json").write_text(doc.to_json(), encoding="utf-8")
    result = replan(directory, settings, listener)

    return {
        "programme_id": programme_id,
        "accepted": accepted,
        "rejected": rejected,
        "minutes": round(result.minutes, 1),
        "lint_errors": len(result.lint.errors),
        "note": (
            "Rejections are the grounding check doing its job, not a bug. Rewrite from the "
            "source sentences and send them again."
            if rejected
            else "All accepted and the programme has been re-planned."
        ),
    }


# -- studying ------------------------------------------------------------------------------------


@mcp.tool(
    title="Start a study session",
    description=(
        "What is due to be reviewed, across every programme or one of them. Ask the questions "
        "one at a time, let the person answer before showing the answer, and call grade_card "
        "for each. Cards you have never seen are introduced a few at a time."
    ),
)
def study_session(
    programme_id: Annotated[str | None, Field(description="Omit for everything due")] = None,
    count: Annotated[int, Field(description="How many questions", ge=1, le=30)] = 8,
) -> dict[str, Any]:
    workspace = _workspace()
    log = review_module.ReviewLog.open(workspace.root)
    state = log.state()

    cards: list[dict[str, Any]] = []
    ids = [programme_id] if programme_id else [str(p["id"]) for p in workspace.list()]
    for pid in ids:
        path = workspace.directory(pid) / "cards.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for card in payload.get("cards", []):
            card["programme_id"] = pid
            cards.append(card)

    chosen, counts = review_module.select(cards, state, count=count)
    return {
        "counts": counts,
        "total_cards": len(cards),
        "questions": [
            {
                "card_id": c.get("id"),
                "programme_id": c.get("programme_id"),
                "concept_id": c.get("concept_id"),
                "subject": c.get("subject"),
                "prompt": c.get("prompt"),
                "answer": c.get("answer"),
                "seen_before": str(c.get("id")) in state,
            }
            for c in chosen
        ],
        "how": (
            "Ask each prompt and wait. Then show the answer and ask whether they got it. Call "
            "grade_card with correct=true or false. Do not show the answer with the question."
        ),
    }


@mcp.tool(
    title="Record an answer",
    description=(
        "Record how a question went and schedule the next showing. A correct answer pushes the "
        "next review further out; a wrong one brings it back to tomorrow."
    ),
)
def grade_card(
    card_id: str,
    programme_id: str,
    correct: bool,
    concept_id: str | None = None,
    note: Annotated[str, Field(description="Anything worth remembering about the attempt")] = "",
) -> dict[str, Any]:
    workspace = _workspace()
    log = review_module.ReviewLog.open(workspace.root)
    answer = log.record(card_id, programme_id, correct, concept_id=concept_id, note=note)
    state = log.state()[card_id]
    return {
        "card_id": card_id,
        "correct": correct,
        "reviews": state.reviews,
        "next_review": state.due_at.date().isoformat(),
        "interval_days": round(answer.interval_days, 1),
    }


@mcp.tool(
    title="Review history",
    description="How the reviewing is going: totals, accuracy, and what is due today.",
)
def review_status() -> dict[str, Any]:
    workspace = _workspace()
    log = review_module.ReviewLog.open(workspace.root)
    answers = log.answers()
    state = log.state()
    now = datetime.now(UTC)
    due = [s for s in state.values() if s.is_due(now)]
    return {
        "answers_recorded": len(answers),
        "cards_started": len(state),
        "accuracy": round(sum(a.correct for a in answers) / len(answers), 2) if answers else None,
        "due_now": len(due),
        "log": str(log.path),
    }


# -- inspecting and correcting -------------------------------------------------------------------


@mcp.tool(
    title="Explain a beat",
    description=(
        "Why does this bit of the programme exist? Returns the design rules that produced it, "
        "the source sentence behind it, and what it cost in seconds. Beat ids are in "
        "manifest.json."
    ),
)
def explain_beat(programme_id: str, beat_id: str) -> dict[str, Any]:
    workspace = _workspace()
    script = _script(workspace, programme_id)
    try:
        beat = script.beat(beat_id)
    except KeyError as exc:
        raise ValueError(f"no beat {beat_id!r} in {programme_id!r}") from exc

    section = script.section_of(beat_id)
    concepts = [script.registry[c].canonical for c in beat.concept_ids if c in script.registry]
    return {
        "type": beat.type.value,
        "rules": beat.rules,
        "written_by": (beat.provenance.generator if beat.provenance else "the source"),
        "section": section.title if section else None,
        "seconds": round(beat.est_seconds, 1),
        "pause_after": round(beat.pause_after, 1),
        "concepts": concepts,
        "spoken": beat.text,
        "source": beat.written_text,
        "pages": sorted({s.page for s in beat.spans if s.page}),
    }


@mcp.tool(
    title="Correct a concept",
    description=(
        "Disagree with how mimem ranked or defined something. Anything set here survives every "
        "future run of this programme. Re-plans afterwards."
    ),
)
def set_concept(
    programme_id: str,
    concept: Annotated[str, Field(description="The concept's name or id")],
    importance: Annotated[float | None, Field(ge=0.0, le=1.0)] = None,
    difficulty: Annotated[float | None, Field(ge=0.0, le=1.0)] = None,
    short_def: str | None = None,
    profile: str = "study",
) -> dict[str, Any]:
    workspace = _workspace()
    directory = workspace.directory(programme_id)
    registry = _registry(workspace, programme_id)

    found = registry.concepts.get(concept) or registry.by_form(concept)
    if found is None:
        near = ", ".join(c.canonical for c in registry.ranked(8))
        raise ValueError(f"no concept {concept!r}. Top concepts: {near}")

    overrides = dict(found.overrides)
    for key, value in (
        ("importance", importance),
        ("difficulty", difficulty),
        ("short_def", short_def),
    ):
        if value is not None:
            overrides[key] = value
    found.overrides = overrides
    found.apply_overrides()

    (directory / "registry.json").write_text(registry.to_json(), encoding="utf-8")
    result = replan(directory, load_profile(profile, _settings()), _listener(None))
    return {
        "concept": found.canonical,
        "overrides": overrides,
        "note": "Stored in registry.json under `overrides`; it survives rebuilding.",
        "minutes": round(result.minutes, 1),
    }


# -- prompts ---------------------------------------------------------------------------------------


@mcp.prompt(
    title="Make a programme from a paper",
    description="Build a listenable programme and write its explanations.",
)
def make_programme(source: str = "") -> str:
    return (
        f"Build a mimem programme from {source or 'the paper I am about to give you'}.\n\n"
        "1. Call build_programme with the path, url or text.\n"
        "2. Tell me what it found: how long it is, how it is structured, what it thinks the "
        "key ideas are, and anything the lint report complains about.\n"
        "3. Call elaboration_plan and write the explanations, concrete images and analogies "
        "yourself, using only the source sentences you are given. Then apply_elaborations.\n"
        "4. If anything is rejected, rewrite it from the source and try again — do not argue "
        "with the check.\n"
        "5. Show me the opening of the finished programme and tell me where the files are."
    )


@mcp.prompt(
    title="Study session",
    description="Quiz me on what is due, and record how it went.",
)
def study(count: str = "8") -> str:
    return (
        f"Run a mimem study session of about {count} questions.\n\n"
        "Call study_session. Then, for each question: ask it, and stop. Wait for my answer "
        "before you show anything. When I have answered, show the real answer, tell me plainly "
        "whether I had it, and call grade_card.\n\n"
        "Do not show the answer with the question, and do not ask them all at once — the pause "
        "where I try to remember is the part that works.\n\n"
        "At the end, tell me what I keep getting wrong."
    )


@mcp.prompt(
    title="Explain a choice",
    description="Why did the programme do that?",
)
def why_this(programme_id: str = "", beat_id: str = "") -> str:
    return (
        f"In the mimem programme {programme_id}, explain why the beat {beat_id} is there. "
        "Call explain_beat, then tell me in plain language which design rule produced it, what "
        "in the paper it came from, and whether mimem wrote it or the authors did."
    )


def main() -> None:
    # The host starts this process with its own environment, which may not be the shell the
    # user set a key in. A `.env` beside the workspace is often the only place it exists.
    from mimem import env as dotenv

    dotenv.load()

    """Run over stdio. Nothing may be written to stdout but the protocol itself."""
    sys.stdout.reconfigure(line_buffering=False)  # type: ignore[union-attr]
    mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
