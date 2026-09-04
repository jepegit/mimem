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


def test_build_is_honest_about_not_being_implemented(paper_pdf: Path) -> None:
    result = runner.invoke(app, ["build", str(paper_pdf)])
    assert result.exit_code == 1
