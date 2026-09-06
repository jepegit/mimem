"""Driving mimem from an assistant: the workspace, the review log, and the server's tools.

The test that matters most is :func:`test_an_invented_number_is_rejected_from_the_conversation`.
The whole design rests on one claim — that letting a chat model write the explanations is safe
because the same deterministic check runs whatever wrote them — and a claim like that is worth
exactly as much as the test behind it.

The tools are called directly rather than over a transport. What is being tested is the
behaviour behind them; that the SDK can carry a dict is the SDK's problem.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mimem.assistant import review as review_module
from mimem.assistant.review import ReviewLog, next_interval, select
from mimem.assistant.server import (
    apply_elaborations,
    build_programme,
    elaboration_plan,
    explain_beat,
    grade_card,
    list_programmes,
    read_programme,
    review_status,
    set_concept,
    study_session,
)
from mimem.assistant.workspace import SourceError, Workspace, resolve_source, slugify

PAPER = (
    "# Interphase repair limits silicon anode life\n\n"
    "Electrolyte decomposition at the negative electrode leads to the formation of a solid "
    "electrolyte interphase, which passivates the surface and limits further reduction. "
    "The solid electrolyte interphase refers to the passivating layer that forms on the "
    "negative electrode during the first charge.\n\n"
    "## 1 Introduction\n\n"
    "Silicon anodes swell on lithiation and the solid electrolyte interphase cracks. "
    "Each repair of the solid electrolyte interphase consumes lithium that never returns. "
    "The thickness of the solid electrolyte interphase increases over the first hundred "
    "cycles. Capacity fade tracks the number of repairs rather than the number of cracks. "
    "The solid electrolyte interphase is therefore the object of this study.\n\n"
    "## 2 Results\n\n"
    "Cells with a thicker solid electrolyte interphase lost capacity faster. "
    "Particle fracture was detected in fewer than one in ten cells. "
    "Lithium inventory, not electrode structure, is what runs out first in these anodes. "
    "The solid electrolyte interphase governs the capacity fade we measure.\n"
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    monkeypatch.setenv("MIMEM_WORKSPACE", str(tmp_path / "ws"))
    return Workspace.open()


@pytest.fixture
def programme(workspace: Workspace) -> dict:
    return build_programme(text=PAPER, name="interphase")


# -- the workspace ---------------------------------------------------------------------------


def test_a_source_can_be_a_path_or_the_text_itself(tmp_path: Path) -> None:
    """Someone in a chat app has the paper as an attachment: the assistant can read it and
    cannot tell you where it is."""
    resolved, arrival = resolve_source(text=PAPER, into=tmp_path)
    assert arrival == "text"
    assert resolved.read_text(encoding="utf-8") == PAPER

    written = tmp_path / "paper.md"
    written.write_text(PAPER, encoding="utf-8")
    resolved, arrival = resolve_source(path=str(written), into=tmp_path)
    assert (resolved, arrival) == (written, "path")


def test_ambiguous_or_missing_sources_are_refused(tmp_path: Path) -> None:
    with pytest.raises(SourceError):
        resolve_source(into=tmp_path)
    with pytest.raises(SourceError):
        resolve_source(path="a.pdf", text=PAPER, into=tmp_path)
    with pytest.raises(SourceError):
        resolve_source(path=str(tmp_path / "nope.pdf"), into=tmp_path)


def test_a_short_text_is_probably_a_path_somebody_mistyped(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="too short"):
        resolve_source(text="~/Downloads/paper.pdf", into=tmp_path)


def test_only_http_can_be_fetched(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="http"):
        resolve_source(url="file:///etc/passwd", into=tmp_path)


def test_a_programme_id_stays_inside_the_workspace(workspace: Workspace) -> None:
    """The id comes from a model. It does not get to name a directory anywhere on the disk."""
    with pytest.raises(SourceError):
        workspace.directory("../../etc")


def test_slugs_are_recognisable(tmp_path: Path) -> None:
    assert (
        slugify("Interphase repair, limits & silicon anodes!")
        == "interphase-repair-limits-silicon-anodes"
    )
    assert slugify("") == "programme"


# -- building through the tool ------------------------------------------------------------------


def test_building_returns_a_summary_not_a_document(programme: dict) -> None:
    """A tool that returned audio.md would fill the conversation and leave no room for the
    conversation."""
    assert programme["title"]
    assert programme["minutes"] > 0
    assert programme["cards"] >= 1
    assert programme["lint_errors"] == 0
    assert "text" not in programme
    assert len(json.dumps(programme)) < 4000


def test_a_built_programme_is_listed(programme: dict, workspace: Workspace) -> None:
    listed = list_programmes()
    assert listed["count"] == 1
    assert listed["programmes"][0]["id"] == programme["id"]


def test_two_builds_do_not_overwrite_each_other(workspace: Workspace) -> None:
    """The older one may be mid-review."""
    first = build_programme(text=PAPER, name="interphase")
    second = build_programme(text=PAPER, name="interphase")
    assert first["id"] != second["id"]


def test_reading_gives_the_outline_first(programme: dict) -> None:
    outline = read_programme(programme["id"])
    assert outline["sections"]
    assert all("title" in s for s in outline["sections"])
    assert "text" not in outline


def test_reading_a_section_is_capped(programme: dict) -> None:
    from mimem.assistant.server import MAX_TEXT_CHARS

    section = read_programme(programme["id"], part="audio", section=0)
    assert section["text"]
    assert len(section["text"]) <= MAX_TEXT_CHARS


def test_an_unknown_section_is_refused(programme: dict) -> None:
    with pytest.raises(ValueError, match="section must be"):
        read_programme(programme["id"], part="audio", section=99)


# -- the elaboration round trip -----------------------------------------------------------------


def test_the_plan_carries_the_source_sentences_and_the_real_instruction(programme: dict) -> None:
    plan = elaboration_plan(programme["id"], limit=3)
    assert plan["tasks"]
    task = plan["tasks"][0]
    assert task["source_sentences"]
    assert task["instruction"]
    assert task["fields"]
    assert plan["house_style"]


def test_a_faithful_elaboration_is_accepted_and_reaches_the_audio(programme: dict) -> None:
    plan = elaboration_plan(programme["id"], limit=6)
    gloss = next(t for t in plan["tasks"] if t["task"] == "gloss")
    result = apply_elaborations(
        programme["id"],
        [
            {
                "task": "gloss",
                "concept_id": gloss["concept_id"],
                "fields": {
                    "short_def": "the passivating layer that forms on the negative electrode",
                    "long_def": (
                        "It forms during the first charge as the electrolyte decomposes, and "
                        "repairing it consumes lithium that never returns."
                    ),
                },
            }
        ],
    )
    assert result["accepted"]
    assert not result["rejected"]
    assert result["lint_errors"] == 0

    audio = read_programme(programme["id"], part="audio")["text"]
    assert "passivating layer" in audio or "first charge" in audio


def test_an_invented_number_is_rejected_from_the_conversation(programme: dict) -> None:
    """The claim the whole design rests on.

    Letting a chat model write the explanations is only safe because the check does not care who
    wrote them. This is the same function the API path calls -- if it stops being the same
    function, this test is what notices.
    """
    plan = elaboration_plan(programme["id"], limit=6)
    gloss = next(t for t in plan["tasks"] if t["task"] == "gloss")
    result = apply_elaborations(
        programme["id"],
        [
            {
                "task": "gloss",
                "concept_id": gloss["concept_id"],
                "fields": {
                    "short_def": "the crust on the negative electrode",
                    "long_def": "It costs 41.85 percent of capacity over five hundred cycles.",
                },
            }
        ],
    )
    assert not result["accepted"]
    assert result["rejected"]
    assert "41.85" in result["rejected"][0]["reason"]
    assert "grounding check doing its job" in result["note"]


def test_a_malformed_answer_is_refused_before_it_is_checked(programme: dict) -> None:
    plan = elaboration_plan(programme["id"], limit=2)
    result = apply_elaborations(
        programme["id"],
        [{"task": "gloss", "concept_id": plan["tasks"][0]["concept_id"], "fields": {"nope": 1}}],
    )
    assert result["rejected"][0]["reason"].startswith("schema")


def test_an_unknown_concept_is_reported_rather_than_ignored(programme: dict) -> None:
    result = apply_elaborations(
        programme["id"],
        [{"task": "gloss", "concept_id": "c_nonexistent", "fields": {}}],
    )
    assert result["rejected"]


# -- studying ------------------------------------------------------------------------------------


def test_a_session_returns_questions_with_their_answers_for_the_assistant(
    programme: dict,
) -> None:
    session = study_session(count=5)
    assert session["questions"]
    first = session["questions"][0]
    assert first["prompt"] and first["answer"]
    assert first["seen_before"] is False
    assert "wait" in session["how"].lower()


def test_grading_schedules_the_next_showing(programme: dict) -> None:
    session = study_session(count=3)
    card = session["questions"][0]
    graded = grade_card(card["card_id"], card["programme_id"], correct=True)
    assert graded["reviews"] == 1
    assert graded["interval_days"] == pytest.approx(1.0)

    again = study_session(count=5)
    assert card["card_id"] not in [q["card_id"] for q in again["questions"]]


def test_a_wrong_answer_brings_it_back_tomorrow(programme: dict) -> None:
    session = study_session(count=3)
    card = session["questions"][0]
    grade_card(card["card_id"], card["programme_id"], correct=True)
    grade_card(card["card_id"], card["programme_id"], correct=True)
    wrong = grade_card(card["card_id"], card["programme_id"], correct=False)
    assert wrong["interval_days"] == pytest.approx(1.0)


def test_the_status_reports_honestly(programme: dict) -> None:
    session = study_session(count=2)
    for card in session["questions"]:
        grade_card(card["card_id"], card["programme_id"], correct=True)
    status = review_status()
    assert status["answers_recorded"] == len(session["questions"])
    assert status["accuracy"] == 1.0


# -- the review log and its scheduler --------------------------------------------------------------


def test_intervals_grow_and_reset() -> None:
    assert next_interval(0, correct=True) == 1.0
    assert next_interval(1.0, correct=True) == pytest.approx(2.5)
    assert next_interval(2.5, correct=True) == pytest.approx(6.25)
    assert next_interval(6.25, correct=False) == 1.0


def test_intervals_stop_growing_eventually() -> None:
    assert next_interval(1_000_000, correct=True) == review_module.MAX_INTERVAL_DAYS


def test_state_is_replayed_from_the_log_not_stored(tmp_path: Path) -> None:
    """So that a better scheduler can be fitted to real answers later without a migration."""
    log = ReviewLog.open(tmp_path)
    log.record("k1", "p1", correct=True)
    log.record("k1", "p1", correct=True)

    reopened = ReviewLog.open(tmp_path)
    state = reopened.state()["k1"]
    assert state.reviews == 2
    assert state.correct == 2
    assert state.interval_days == pytest.approx(2.5)


def test_a_corrupt_line_loses_one_answer_not_the_history(tmp_path: Path) -> None:
    log = ReviewLog.open(tmp_path)
    log.record("k1", "p1", correct=True)
    with log.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
    log.record("k2", "p1", correct=True)

    assert set(ReviewLog.open(tmp_path).state()) == {"k1", "k2"}


def test_due_cards_come_before_new_ones(tmp_path: Path) -> None:
    log = ReviewLog.open(tmp_path)
    yesterday = datetime.now(UTC) - timedelta(days=3)
    log.record("due", "p1", correct=True, now=yesterday)

    cards = [{"id": "due"}, {"id": "fresh-a"}, {"id": "fresh-b"}]
    chosen, counts = select(cards, log.state(), count=2)
    assert chosen[0]["id"] == "due"
    assert counts == {"due": 1, "new": 2, "returned": 2}


def test_new_cards_are_introduced_a_few_at_a_time(tmp_path: Path) -> None:
    """A freshly built programme has sixty cards, and starting all of them at once produces
    sixty cards all due tomorrow."""
    cards = [{"id": f"k{i}"} for i in range(40)]
    chosen, _ = select(cards, {}, count=30, max_new=6)
    assert len(chosen) == 6


# -- inspecting and correcting -----------------------------------------------------------------


def test_a_beat_explains_itself(programme: dict) -> None:
    from mimem.ir import Script

    workspace = Workspace.open()
    script = Script.from_json((workspace.directory(programme["id"]) / "script.json").read_bytes())
    beat = next(b for b in script.beats() if b.type.value == "exposition")

    explained = explain_beat(programme["id"], beat.id)
    assert explained["rules"]
    assert explained["spoken"]
    assert explained["written_by"] == "the source"


def test_an_unknown_beat_says_so(programme: dict) -> None:
    with pytest.raises(ValueError, match="no beat"):
        explain_beat(programme["id"], "t_nope")


def test_a_correction_survives_in_the_registry(programme: dict) -> None:
    from mimem.ir import ConceptRegistry

    workspace = Workspace.open()
    registry = ConceptRegistry.from_json(
        (workspace.directory(programme["id"]) / "registry.json").read_bytes()
    )
    concept = registry.ranked()[0]

    result = set_concept(programme["id"], concept.canonical, importance=0.99)
    assert result["overrides"]["importance"] == 0.99

    reloaded = ConceptRegistry.from_json(
        (workspace.directory(programme["id"]) / "registry.json").read_bytes()
    )
    assert reloaded.concepts[concept.id].importance == pytest.approx(0.99)


def test_correcting_an_unknown_concept_suggests_the_real_ones(programme: dict) -> None:
    with pytest.raises(ValueError, match="Top concepts"):
        set_concept(programme["id"], "something nobody wrote about")


# -- the protocol ----------------------------------------------------------------------------------


@pytest.mark.slow
def test_the_server_speaks_the_protocol(tmp_path: Path) -> None:
    """Everything else here calls the tool functions directly, which proves the behaviour and
    not the wiring. This starts the real server over stdio and drives it with a real client, so
    that "it works in Claude Desktop" rests on something.
    """
    import asyncio
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def drive() -> tuple[dict, dict]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mimem.assistant.server"],
            env={**os.environ, "MIMEM_WORKSPACE": str(tmp_path / "ws")},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            built = _unpack(
                await session.call_tool("build_programme", {"text": PAPER, "name": "wire"})
            )
            plan = _unpack(
                await session.call_tool(
                    "elaboration_plan", {"programme_id": built["id"], "limit": 3}
                )
            )
            gloss = next(t for t in plan["tasks"] if t["task"] == "gloss")
            rejected = _unpack(
                await session.call_tool(
                    "apply_elaborations",
                    {
                        "programme_id": built["id"],
                        "answers": [
                            {
                                "task": "gloss",
                                "concept_id": gloss["concept_id"],
                                "fields": {
                                    "short_def": "the crust on the anode",
                                    "long_def": "It costs 41.85 percent of capacity.",
                                },
                            }
                        ],
                    },
                )
            )
            return {"tools": len(listed.tools), **built}, rejected

    built, rejected = asyncio.run(drive())
    assert built["tools"] >= 8
    assert built["lint_errors"] == 0
    assert rejected["rejected"], "the gate did not fire over the wire"
    assert "41.85" in rejected["rejected"][0]["reason"]


def _unpack(result: object) -> dict:
    structured = getattr(result, "structured_content", None)
    if structured:
        return dict(structured)
    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if text:
            return dict(json.loads(text))
    raise AssertionError("the tool returned nothing usable")


def test_importing_the_server_writes_nothing_to_stdout() -> None:
    """An MCP stdio server speaks protocol on stdout. One stray banner and the client sees an
    unexplained disconnection."""
    import subprocess
    import sys

    # A subprocess rather than a redirect: an import-time print in a dependency would be
    # captured by a redirect inside this process too, but only a real interpreter start shows
    # what the MCP client would actually receive.
    result = subprocess.run(
        [sys.executable, "-c", "import mimem.assistant.server"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == ""
