from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from mimem.cli import app

runner = CliRunner()


def test_version_lists_readable_formats() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert ".pdf" in result.stdout


def test_profiles_shows_the_shipped_profiles() -> None:
    result = runner.invoke(app, ["profiles"])
    assert result.exit_code == 0
    for name in ("skim", "study", "drill"):
        assert name in result.stdout
    assert "exact" in result.stdout  # rule NUM-01


def test_ingest_then_inspect(paper_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "paper.ir.json"
    assert runner.invoke(app, ["ingest", str(paper_pdf), "-o", str(out)]).exit_code == 0
    assert out.exists()

    result = runner.invoke(app, ["inspect", str(out)])
    assert result.exit_code == 0
    assert "outline" in result.stdout
    assert "1. Introduction" in result.stdout


def test_ingest_can_skip_the_clean_stage(paper_pdf: Path, tmp_path: Path) -> None:
    from mimem.ir import Document

    out = tmp_path / "raw.ir.json"
    runner.invoke(app, ["ingest", str(paper_pdf), "-o", str(out), "--no-clean"])
    assert Document.from_json(out.read_bytes()).stages == ["ingest"]

    runner.invoke(app, ["clean", str(out)])
    assert Document.from_json(out.read_bytes()).stages == ["ingest", "clean"]


def test_missing_source_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ingest", str(tmp_path / "nope.pdf")])
    assert result.exit_code == 1


def test_build_runs_the_whole_pipeline(paper_pdf: Path, tmp_path: Path) -> None:
    """Source document in, listenable programme out, with the lint report as the gate."""
    out = tmp_path / "programme"
    result = runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    for name in ("audio.md", "study.md", "cards.json", "manifest.json", "script.json"):
        assert (out / name).exists(), name
    assert "min against" in result.stdout


def test_build_keeps_the_intermediate_stages_on_disk(paper_pdf: Path, tmp_path: Path) -> None:
    """Every stage is a file-to-file transform: you can stop, edit, and resume (PLAN section 1)."""
    out = tmp_path / "programme"
    runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)])
    assert (out / "doc.ir.json").exists()
    assert (out / "registry.json").exists()
    assert (out / "drop-report.md").exists()


def test_plan_then_render_then_lint(paper_pdf: Path, tmp_path: Path) -> None:
    ir = tmp_path / "paper.ir.json"
    runner.invoke(app, ["ingest", str(paper_pdf), "-o", str(ir)])
    script = tmp_path / "paper.script.json"

    assert runner.invoke(app, ["plan", str(ir), "-o", str(script)]).exit_code == 0
    out = tmp_path / "out"
    assert runner.invoke(app, ["render", str(script), "-o", str(out)]).exit_code == 0
    assert runner.invoke(app, ["lint", str(out)]).exit_code == 0


def test_explain_traces_a_beat_back_to_its_rule_and_its_source(
    paper_pdf: Path, tmp_path: Path
) -> None:
    """Without this, tuning the system is guesswork (PLAN section 1)."""
    from mimem.ir import Script

    out = tmp_path / "programme"
    runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)])
    script = Script.from_json((out / "script.json").read_bytes())
    beat = next(b for b in script.beats() if b.type.value == "exposition")

    result = runner.invoke(app, ["explain", str(out), "--beat", beat.id])
    assert result.exit_code == 0
    assert "exposition" in result.stdout
    assert "source" in result.stdout


def test_explain_rejects_an_unknown_beat(paper_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "programme"
    runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)])
    assert runner.invoke(app, ["explain", str(out), "--beat", "t_nope"]).exit_code == 1


def test_lint_on_a_bare_audio_file_says_what_it_cannot_check(tmp_path: Path) -> None:
    audio = tmp_path / "audio.md"
    audio.write_text("This is a clean sentence.\n", encoding="utf-8")
    result = runner.invoke(app, ["lint", str(audio)])
    assert result.exit_code == 0
    assert "text rules only" in result.stdout


def test_build_can_go_all_the_way_to_audio(paper_pdf: Path, tmp_path: Path) -> None:
    """Milestone M7's acceptance test: one command, PDF to a playable file."""
    import wave

    out = tmp_path / "programme"
    result = runner.invoke(app, ["build", str(paper_pdf), "--out", str(out), "--speak", "silent"])
    assert result.exit_code == 0, result.stdout
    assert (out / "audio.wav").exists()
    assert (out / "timings.json").exists()
    with wave.open(str(out / "audio.wav")) as handle:
        assert handle.getnframes() > 0
    assert "of audio" in result.stdout


def test_speak_runs_on_a_programme_directory(paper_pdf: Path, tmp_path: Path) -> None:
    """`mimem speak out/paper` finds the script itself, like `explain` does."""
    out = tmp_path / "programme"
    assert runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)]).exit_code == 0
    assert not (out / "audio.wav").exists()

    result = runner.invoke(app, ["speak", str(out), "--engine", "silent"])
    assert result.exit_code == 0, result.stdout
    assert (out / "audio.wav").exists()


def test_speaking_twice_reuses_the_cache(paper_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "programme"
    runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)])
    runner.invoke(app, ["speak", str(out), "--engine", "silent"])
    again = runner.invoke(app, ["speak", str(out), "--engine", "silent"])
    assert "0 beats synthesised" in again.stdout


def test_an_unknown_engine_is_a_clean_error(paper_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "programme"
    runner.invoke(app, ["build", str(paper_pdf), "--out", str(out)])
    result = runner.invoke(app, ["speak", str(out), "--engine", "nope"])
    assert result.exit_code == 1
    assert "unknown engine" in result.stdout + str(result.stderr or "")
