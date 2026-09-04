"""Command line interface.

Every stage is a file-to-file transform, so that you can stop after any of them, edit the
intermediate JSON by hand, and resume (PLAN section 1). ``inspect`` is not a debugging
afterthought -- it is how you find out that ingestion quietly ate the methods section.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mimem import __version__
from mimem.clean import clean as run_clean
from mimem.config import Settings, load_listener, load_profile
from mimem.ingest import IngestError, available_extensions
from mimem.ingest import load as run_ingest
from mimem.ir import Block, BlockKind, BlockRole, DiagnosticLevel, Document
from mimem.lint import LintReport, Severity
from mimem.lint import lint as run_lint
from mimem.render import narrate as run_narrate
from mimem.triage import drop_report
from mimem.triage import triage as run_triage

app = typer.Typer(
    name="mimem",
    help="Convert your library into audio that is designed for remembering.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


def _fail(message: str) -> None:
    err.print(f"[bold red]error[/] {message}")
    raise typer.Exit(code=1)


def _read_document(path: Path) -> Document:
    try:
        return Document.from_json(path.read_bytes())
    except Exception as exc:
        _fail(f"{path} is not a mimem document: {exc}")
        raise  # unreachable, keeps type checkers happy


def _write_document(doc: Document, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc.to_json(), encoding="utf-8")
    console.print(f"[green]wrote[/] {out}  ({len(doc.blocks)} blocks, {doc.word_count} words)")


@app.command()
def version() -> None:
    """Print the version and the formats this build can read."""
    console.print(f"mimem {__version__}")
    console.print(f"formats: {', '.join(available_extensions())}")


@app.command()
def ingest(
    source: Annotated[Path, typer.Argument(help="PDF, EPUB, Markdown or text file")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="output IR JSON")] = None,
    clean_after: Annotated[
        bool, typer.Option("--clean/--no-clean", help="run stage 2 immediately")
    ] = True,
) -> None:
    """Stage 1 (+2): read a source document into the canonical IR."""
    try:
        doc = run_ingest(source)
    except IngestError as exc:
        _fail(str(exc))
        return
    if clean_after:
        doc = run_clean(doc)
    _write_document(doc, out or source.with_suffix(".ir.json"))
    _print_diagnostics(doc)


@app.command()
def clean(
    ir: Annotated[Path, typer.Argument(help="IR JSON from `mimem ingest --no-clean`")],
    out: Annotated[Path | None, typer.Option("--out", "-o")] = None,
) -> None:
    """Stage 2: dehyphenate, strip page furniture, rejoin paragraphs, assign sections."""
    doc = run_clean(_read_document(ir))
    _write_document(doc, out or ir)
    _print_diagnostics(doc)


@app.command()
def inspect(
    ir: Annotated[Path, typer.Argument(help="IR JSON")],
    outline: Annotated[bool, typer.Option("--outline", help="show the section outline")] = True,
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    show: Annotated[int, typer.Option("--show", help="print the first N body blocks verbatim")] = 0,
) -> None:
    """Show what ingestion actually produced. Read this before trusting a build."""
    doc = _read_document(ir)
    settings = Settings()
    try:
        profile = load_profile(profile_name, settings)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return

    src = doc.source
    console.print(f"[bold]{src.title or '(untitled)'}[/]")
    meta = [
        f"format={src.format}",
        f"adapter={src.adapter}/{src.adapter_version}",
        f"pages={src.n_pages or '-'}",
        f"blocks={len(doc.blocks)}",
        f"words={doc.word_count}",
        f"stages={'>'.join(doc.stages) or '-'}",
    ]
    if src.doi:
        meta.append(f"doi={src.doi}")
    console.print("  " + "  ".join(meta), style="dim")

    seconds = profile.seconds_for(" ".join(b.text for b in _spoken_candidates(doc)))
    console.print(
        f"  straight read of retained prose: [bold]{seconds / 60:.1f} min[/] "
        f"at {profile.wpm:.0f} wpm",
        style="dim",
    )

    _print_counts(doc)
    if outline:
        _print_outline(doc)
    if show:
        _print_sample(doc, show)
    _print_diagnostics(doc)


@app.command()
def profiles() -> None:
    """List the available profiles and their headline settings."""
    settings = Settings()
    table = Table("profile", "wpm", "duration x", "prompts/segment", "repeats", "numbers")
    for path in sorted(settings.profiles_dir.glob("*.yaml")):
        p = load_profile(path.stem, settings)
        table.add_row(
            p.name,
            f"{p.wpm:.0f}",
            f"{p.duration_multiplier:.1f}",
            str(p.prompts_per_segment),
            f"{p.spacing.repetitions_min}-{p.spacing.repetitions_max}",
            p.numeric_fidelity.value,
        )
    console.print(table)
    listener = load_listener(settings=settings)
    console.print(f"listener: [bold]{listener.name}[/] ({len(listener.known_terms)} known terms)")


@app.command()
def triage(
    ir: Annotated[Path, typer.Argument(help="IR JSON")],
    out: Annotated[Path | None, typer.Option("--out", "-o")] = None,
    report: Annotated[
        Path | None, typer.Option("--report", help="write the drop report here")
    ] = None,
) -> None:
    """Stage 3: decide what reaches the narration, and record why (rules COH-*)."""
    doc = run_triage(_read_document(ir))
    _write_document(doc, out or ir)
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(drop_report(doc), encoding="utf-8")
        console.print(f"[green]wrote[/] {report}")
    _print_diagnostics(doc)


@app.command()
def narrate(
    ir: Annotated[Path, typer.Argument(help="IR JSON")],
    out_dir: Annotated[Path, typer.Option("--out", "-o", help="output directory")] = Path("out"),
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
    check: Annotated[bool, typer.Option("--lint/--no-lint", help="lint the result")] = True,
) -> None:
    """Stages 3, 5 and 8: retained content, verbalized, as narration text.

    This is a straight reading, not the memorable version -- prequestions, retrieval beats,
    anchors and spacing arrive with M4. What it proves is that nothing unspeakable survives.
    """
    settings = Settings()
    try:
        profile = load_profile(profile_name, settings)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    listener = load_listener(listener_file, settings)

    doc = run_triage(_read_document(ir))
    narration = run_narrate(doc, profile, listener)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audio.md").write_text(narration.audio, encoding="utf-8")
    (out_dir / "study.md").write_text(narration.study, encoding="utf-8")
    (out_dir / "drop-report.md").write_text(drop_report(doc), encoding="utf-8")

    minutes = narration.estimated_seconds(profile) / 60
    console.print(
        f"[green]wrote[/] {out_dir}/audio.md  "
        f"({narration.spoken_words} words, about {minutes:.1f} min at {profile.wpm:.0f} wpm)"
    )
    if narration.pending:
        pending = ", ".join(f"{n} {kind}" for kind, n in sorted(narration.pending.items()))
        console.print(f"  [yellow]awaiting M5 verbalizers:[/] {pending}", style="dim")
    if check:
        _report_lint(run_lint(narration.audio))


@app.command()
def lint(
    target: Annotated[Path, typer.Argument(help="audio.md, or a directory containing it")],
) -> None:
    """Stage 9: check narration text against the design rules."""
    path = target / "audio.md" if target.is_dir() else target
    if not path.exists():
        _fail(f"no such file: {path}")
        return
    report = run_lint(path.read_text(encoding="utf-8"))
    _report_lint(report)
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def build(
    source: Annotated[Path, typer.Argument()],
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
) -> None:
    """Full pipeline. Not available yet -- the learning-design stages land in M4-M6."""
    _fail(
        "`build` needs stages 4, 6 and 7 (concepts, elaboration, planning), which are not "
        "implemented yet -- see docs/PLAN-part1.md. Today: `mimem ingest` then `mimem narrate`."
    )


def _report_lint(report: LintReport, examples: int = 3) -> None:
    """Print a lint report: counts first, then a few examples of each rule."""
    if report.ok and not report.warnings:
        console.print(f"[green]lint clean[/] ({len(report.checked_rules)} rules)")
        return
    style = "bold red" if not report.ok else "yellow"
    console.print(f"[{style}]lint:[/] {report.summary()}")
    seen: dict[str, int] = {}
    for v in report.violations:
        seen[v.rule] = seen.get(v.rule, 0) + 1
        if seen[v.rule] > examples:
            continue
        colour = "red" if v.severity is Severity.ERROR else "yellow"
        console.print(f"  [{colour}]{v.rule}[/] line {v.line}: {v.message}", style="dim")
        console.print(f"      …{v.excerpt}…", style="dim")


# -- printing helpers --------------------------------------------------------------------


def _spoken_candidates(doc: Document) -> list[Block]:
    """Blocks that would plausibly reach the narration, for a rough duration estimate."""
    from mimem.ir import NON_CONTENT_ROLES

    skip_kinds = {BlockKind.PAGE_ARTIFACT, BlockKind.REFERENCE, BlockKind.FIGURE}
    return [
        b
        for b in doc.blocks
        if b.kind not in skip_kinds and b.role not in NON_CONTENT_ROLES and b.text.strip()
    ]


def _print_counts(doc: Document) -> None:
    kinds = Counter(b.kind.value for b in doc.blocks)
    roles = Counter(b.role.value for b in doc.blocks)
    table = Table("kind", "n", "role", "n", title="blocks", title_style="bold")
    kind_rows = kinds.most_common()
    role_rows = roles.most_common()
    for i in range(max(len(kind_rows), len(role_rows))):
        k = kind_rows[i] if i < len(kind_rows) else ("", "")
        r = role_rows[i] if i < len(role_rows) else ("", "")
        table.add_row(str(k[0]), str(k[1]), str(r[0]), str(r[1]))
    console.print(table)


def _print_outline(doc: Document) -> None:
    headings = [b for b in doc.blocks if b.kind is BlockKind.HEADING]
    if not headings:
        console.print("[yellow]no headings found[/] -- section structure will be flat", style="dim")
        return
    console.print("[bold]outline[/]")
    for h in headings:
        indent = "  " * ((h.level or 1) - 1)
        role = (
            "" if h.role in {BlockRole.BODY, BlockRole.UNKNOWN} else f"  [dim]<{h.role.value}>[/]"
        )
        page = f" [dim]p{h.page}[/]" if h.page else ""
        console.print(f"  {indent}{h.text.strip()[:80]}{role}{page}")


def _print_sample(doc: Document, n: int) -> None:
    console.print("[bold]sample[/]")
    shown = 0
    for b in _spoken_candidates(doc):
        if b.kind is BlockKind.HEADING:
            continue
        console.print(f"  [dim]{b.role.value}/{b.kind.value}[/] {b.text[:400]}")
        shown += 1
        if shown >= n:
            break


def _print_diagnostics(doc: Document) -> None:
    if not doc.diagnostics:
        return
    styles = {
        DiagnosticLevel.INFO: "dim",
        DiagnosticLevel.WARNING: "yellow",
        DiagnosticLevel.ERROR: "bold red",
    }
    for d in doc.diagnostics:
        where = f" (p{d.page})" if d.page else ""
        console.print(f"  [{d.stage}] {d.code}: {d.message}{where}", style=styles[d.level])


if __name__ == "__main__":  # pragma: no cover
    app()
