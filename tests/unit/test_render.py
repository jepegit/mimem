"""The four artefacts.

The interesting property is not that each renderer produces text -- it is that ``audio.md`` and
``study.md`` are *different*, in the specific ways the knowledge base (§4.6) and rules ``NUM-06``
and ``GRD-04`` require. The audio track drops what cannot be spoken; the written track keeps it,
with a page number, so nothing exact is ever destroyed by the act of saying it out loud.
"""

from __future__ import annotations

import json
from pathlib import Path

from mimem.ir import BeatType, Script
from mimem.lint import lint
from mimem.render import render, render_audio, render_cards, render_manifest, render_study


def test_the_audio_track_is_only_what_gets_said(interphase_script: Script) -> None:
    audio = render_audio(interphase_script)
    assert "<sub>" not in audio
    assert "p1" not in audio.split()
    for beat in interphase_script.beats():
        if beat.text.strip():
            assert beat.text.strip() in audio


def test_the_audio_track_passes_the_speakability_rules(interphase_script: Script) -> None:
    """The whole point of stage 5 and of the scaffolding templates going through it."""
    report = lint(render_audio(interphase_script))
    assert report.ok, report.summary()


def test_the_written_track_keeps_what_the_audio_dropped(interphase_script: Script) -> None:
    """Rules NUM-06 and GRD-04: the exact source, and a page to open."""
    study = render_study(interphase_script)
    source_sentence = next(
        b.written_text
        for b in interphase_script.beats()
        if b.type is BeatType.EXPOSITION and b.written_text
    )
    assert source_sentence.split(".")[0] in study
    assert "<sub>p" in study  # a locator on the grounded beats


def test_the_two_tracks_are_not_the_same_document(interphase_script: Script) -> None:
    assert render_audio(interphase_script) != render_study(interphase_script)


def test_the_written_track_marks_who_wrote_each_beat(interphase_script: Script) -> None:
    """Rule VOI-02: a reader is never in doubt about whose claim they are reading."""
    study = render_study(interphase_script)
    assert "*orientation:*" in study
    assert "**Q.**" in study and "**A.**" in study


def test_cards_carry_everything_part_two_needs(interphase_script: Script) -> None:
    payload = json.loads(render_cards(interphase_script))
    assert payload["cards"]
    for card in payload["cards"]:
        assert card["prompt"] and card["answer"]
        assert card["concept_id"]
        assert card["prompt_type"] in {
            "definition",
            "mechanism",
            "distinction",
            "value",
            "recall",
        }
        assert card["spans"]  # rule RET-05: the source of the answer


def test_the_manifest_is_the_audit_trail(interphase_script: Script) -> None:
    payload = json.loads(render_manifest(interphase_script))
    assert payload["duration"]["estimated_seconds"] > 0
    assert payload["concepts"]
    first = next(iter(payload["concepts"].values()))
    assert "signals" in first  # rule DIF-01: the scores are auditable
    assert first["exposures"]  # rule SPC-03
    assert payload["schedule"]


def test_every_chunk_is_addressable_and_timed(interphase_script: Script) -> None:
    """Rule TTS-03: part two re-synthesises only the beats that changed."""
    chunks = json.loads(render_manifest(interphase_script))["chunks"]
    assert chunks
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert all(len(c["sha256"]) == 64 for c in chunks)
    assert chunks == sorted(chunks, key=lambda c: c["at_seconds"])


def test_pauses_live_in_the_manifest_not_in_the_audio(interphase_script: Script) -> None:
    """A break marker inside audio.md is either unspeakable or spoken aloud (rules TTS-01/02)."""
    chunks = json.loads(render_manifest(interphase_script))["chunks"]
    assert any(c["pause_after"] > 0 for c in chunks)
    assert "break" not in render_audio(interphase_script).lower()


def test_writing_produces_the_four_files(interphase_script: Script, tmp_path: Path) -> None:
    written = render(interphase_script).write(tmp_path)
    assert {p.name for p in written} == {
        "audio.md",
        "study.md",
        "cards.json",
        "manifest.json",
    }
    assert all(p.read_text(encoding="utf-8").strip() for p in written)


def test_the_cut_beats_are_listed_where_a_reader_will_find_them(
    interphase_script: Script,
) -> None:
    """Rule COH-05: nothing vanishes silently, including our own scaffolding."""
    from mimem.plan.budget import enforce

    enforce(interphase_script, budget=1.0)
    study = render_study(interphase_script)
    assert "Cut to fit the duration budget" in study
