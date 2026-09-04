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
def build(
    source: Annotated[Path, typer.Argument()],
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
) -> None:
    """Full pipeline. Not available yet -- stages 3-9 land in M2-M6."""
    _fail(
        "`build` needs stages 3-9, which are not implemented yet (see docs/PLAN-part1.md). "
        "Use `mimem ingest` and `mimem inspect` today."
    )


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
