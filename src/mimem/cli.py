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
from mimem.concepts import build as build_registry
from mimem.concepts import norms
from mimem.config import Listener, Profile, Settings, load_listener, load_profile
from mimem.elaborate import elaborate as run_elaborate
from mimem.elaborate import plan_requests
from mimem.ingest import IngestError, available_extensions
from mimem.ingest import load as run_ingest
from mimem.ir import (
    Block,
    BlockKind,
    BlockRole,
    ConceptRegistry,
    DiagnosticLevel,
    Document,
    Script,
)
from mimem.lint import LintReport, Severity
from mimem.lint import lint as run_lint
from mimem.lint import lint_script as run_lint_script
from mimem.llm import Cached, Client, FixtureClient, NullClient
from mimem.llm.cost import BudgetExceededError
from mimem.pipeline import build_all
from mimem.plan import plan as run_plan
from mimem.render import narrate as run_narrate
from mimem.render import render as run_render
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
def concepts(
    ir: Annotated[Path, typer.Argument(help="IR JSON")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="registry JSON")] = None,
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
    top: Annotated[int, typer.Option("--top", help="how many to print")] = 20,
) -> None:
    """Stage 4: extract the concepts and score them by difficulty and importance.

    The registry it writes is meant to be edited. Anything you put under a concept's
    ``overrides`` key survives the next run, so correcting a bad ranking is a one-line change
    rather than an argument with a heuristic.
    """
    doc = _read_document(ir)
    settings = Settings()
    listener = load_listener(listener_file, settings)

    target = out or ir.with_name(ir.stem.replace(".ir", "") + ".registry.json")
    previous = None
    if target.exists():
        try:
            previous = ConceptRegistry.from_json(target.read_bytes())
        except Exception as exc:  # a corrupt registry should not lose the run
            console.print(f"[yellow]ignoring unreadable registry[/] {target}: {exc}", style="dim")

    registry = build_registry(doc, listener, previous)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(registry.to_json(), encoding="utf-8")

    norms_status = norms.status()
    console.print(f"[green]wrote[/] {target}  ({len(registry.concepts)} concepts)")
    console.print(
        f"  concreteness from [bold]{norms_status.source}[/]"
        + (f" ({norms_status.entries} words)" if norms_status.entries else " (no norms file)"),
        style="dim",
    )
    if norms_status.source == "morphology":
        console.print(
            "  for measured scores, put the Brysbaert 2014 concreteness CSV at "
            "data/concreteness.csv or set MIMEM_CONCRETENESS_FILE",
            style="dim",
        )

    table = Table("concept", "diff", "impt", "budget", "n", "kind", title=f"top {top}")
    for c in registry.ranked(top):
        table.add_row(
            c.canonical[:44],
            f"{c.difficulty:.2f}",
            f"{c.importance:.2f}",
            f"{c.budget:.3f}",
            str(c.mentions),
            c.kind.value,
        )
    console.print(table)
    if listener.name != "default":
        console.print(f"scored for listener [bold]{listener.name}[/]", style="dim")


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
    target: Annotated[Path, typer.Argument(help="a build directory, audio.md, or script.json")],
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
) -> None:
    """Stage 9: the acceptance test.

    Given a build directory it checks both halves -- the narration text against the speakability
    rules, and the plan against the structure, retrieval and spacing rules. Given a bare
    ``audio.md`` it can only do the first, and says so.
    """
    settings = Settings()
    profile, _ = _profile_and_listener(profile_name, None, settings)

    script_file = _find_script(target)
    if script_file is not None:
        script = _read_script(script_file)
        audio = target / "audio.md" if target.is_dir() else None
        report = run_lint_script(
            script,
            audio.read_text(encoding="utf-8") if audio and audio.exists() else None,
            profile,
        )
    else:
        path = target / "audio.md" if target.is_dir() else target
        if not path.exists():
            _fail(f"no such file: {path}")
            return
        console.print("[dim]text rules only; no script.json here to check the structure[/]")
        report = run_lint(path.read_text(encoding="utf-8"))

    _report_lint(report)
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def elaborate(
    ir: Annotated[Path, typer.Argument(help="triaged IR JSON")],
    registry_file: Annotated[
        Path | None, typer.Option("--registry", help="registry JSON; built if absent")
    ] = None,
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="print the planned calls and stop")
    ] = False,
    fixtures: Annotated[
        Path | None, typer.Option("--fixtures", help="replay recorded answers from here")
    ] = None,
    live: Annotated[
        bool, typer.Option("--llm/--local", help="call a model, or run deterministic-only")
    ] = False,
    model: Annotated[str | None, typer.Option("--model")] = None,
    budget: Annotated[float | None, typer.Option("--budget", help="hard cap in US dollars")] = None,
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
) -> None:
    """Stage 6: glosses, concrete anchors, why-explanations and analogies.

    Nothing here is billed unless you ask for it: the default is ``--local``, which runs every
    task's degradation path and reports what it skipped. ``--dry-run`` prints the calls and an
    estimate without making any. ``--budget`` stops the run rather than surprising you.

    Everything a model writes is checked against the sentences it was written from before it is
    stored -- a number the source does not state is rejected, not warned about.
    """
    settings = Settings()
    profile, listener = _profile_and_listener(profile_name, listener_file, settings)
    doc = run_triage(_read_document(ir))
    target = registry_file or ir.with_name(ir.stem.replace(".ir", "") + ".registry.json")
    registry = _load_or_build_registry(doc, registry_file, ir, listener)

    if dry_run:
        planned = plan_requests(doc, registry, profile, listener)
        console.print(planned.report())
        console.print(planned.report(batch=True), style="dim")
        return

    client = _make_client(fixtures, live, model, settings, no_cache)
    try:
        report = run_elaborate(doc, registry, profile, listener, client, budget=budget)
    except BudgetExceededError as exc:
        _fail(str(exc))
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(registry.to_json(), encoding="utf-8")
    console.print(f"[green]wrote[/] {target}")
    _print_elaboration(report)


@app.command()
def plan(
    ir: Annotated[Path, typer.Argument(help="triaged IR JSON")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="script JSON")] = None,
    registry_file: Annotated[
        Path | None, typer.Option("--registry", help="registry JSON; built if absent")
    ] = None,
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
) -> None:
    """Stage 7: lay out the beats, the segments, the prompts and the spacing.

    This is where the design rules become structure: an orientation block, a term pre-load,
    sections that end on a question, concepts that come back at increasing intervals, and a
    review that interleaves. No model is called; everything here is a source sentence or a
    named template.
    """
    settings = Settings()
    profile, listener = _profile_and_listener(profile_name, listener_file, settings)
    doc = run_triage(_read_document(ir))

    registry = _load_or_build_registry(doc, registry_file, ir, listener)
    script = run_plan(doc, registry, profile, listener)

    target = out or ir.with_name(ir.stem.replace(".ir", "") + ".script.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(script.to_json(), encoding="utf-8")
    console.print(f"[green]wrote[/] {target}")
    _print_script_summary(script, profile)


@app.command()
def render(
    script_file: Annotated[Path, typer.Argument(help="script JSON from `mimem plan`")],
    out_dir: Annotated[Path, typer.Option("--out", "-o", help="output directory")] = Path("out"),
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    check: Annotated[bool, typer.Option("--lint/--no-lint", help="lint the result")] = True,
) -> None:
    """Stage 8: audio.md, study.md, cards.json and manifest.json."""
    settings = Settings()
    script = _read_script(script_file)
    profile, _ = _profile_and_listener(profile_name, None, settings)

    artefacts = run_render(script)
    written = artefacts.write(out_dir)
    for path in written:
        console.print(f"[green]wrote[/] {path}")
    if check:
        _report_lint(run_lint_script(script, artefacts.audio, profile))


@app.command()
def explain(
    target: Annotated[Path, typer.Argument(help="script JSON, or a directory containing one")],
    beat: Annotated[str, typer.Option("--beat", help="beat ID from manifest.json")],
) -> None:
    """Why does this beat exist? Which rule produced it, and from which source span.

    The plan calls for this from day one, and the reason is tuning: without it, every judgement
    about the output is an argument about a black box.
    """
    script = _read_script(_script_path(target))
    try:
        found = script.beat(beat)
    except KeyError:
        _fail(f"no beat {beat} in {target}")
        return

    console.print(f"[bold]{found.type.value}[/]  {found.id}")
    console.print(f"  rules: {', '.join(found.rules) or '-'}", style="dim")
    console.print(
        f"  {found.est_seconds:.1f}s speech, {found.pause_after:.1f}s pause, "
        f"{'generated' if found.generated else 'from the source'}",
        style="dim",
    )
    if found.provenance:
        console.print(f"  written by: {found.provenance.generator}", style="dim")
    section = script.section_of(found.id)
    if section:
        console.print(f"  section: {section.title}", style="dim")
    for concept_id in found.concept_ids:
        concept = script.registry.get(concept_id)
        if concept:
            console.print(
                f"  concept: {concept.canonical} "
                f"(difficulty {concept.difficulty:.2f}, importance {concept.importance:.2f})",
                style="dim",
            )
    console.print(f"\n{found.text}\n")

    doc = _sibling_document(target)
    for span in found.spans:
        where = f"p{span.page}" if span.page else span.block_id[:10]
        console.print(f"[bold]source[/] {where}", style="dim")
        if doc is not None:
            try:
                console.print(f"  {doc.text_of(span).strip()}")
            except KeyError:
                console.print("  (block not in the sibling IR)", style="dim")


@app.command()
def build(
    source: Annotated[Path, typer.Argument(help="PDF, EPUB, Markdown or text file")],
    out_dir: Annotated[Path, typer.Option("--out", "-o", help="output directory")] = Path("out"),
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
    fixtures: Annotated[
        Path | None, typer.Option("--fixtures", help="replay recorded elaborations from here")
    ] = None,
    live: Annotated[
        bool, typer.Option("--llm/--local", help="call a model for stage 6, or skip it")
    ] = False,
    budget: Annotated[float | None, typer.Option("--budget", help="hard cap in US dollars")] = None,
) -> None:
    """The whole pipeline: source document to a listenable, checkable programme.

    Stage 6 is off by default. With ``--local`` you get the paper said in a way you can follow,
    with the questions and the spacing that make it stick; with ``--llm`` you also get the
    glosses, the concrete anchors and the analogies, and a bill.
    """
    settings = Settings()
    profile, listener = _profile_and_listener(profile_name, listener_file, settings)

    # The nine stages live in `mimem.pipeline`, shared with the assistant server: two copies of
    # that sequence would drift the first time a stage moved.
    client = (
        _make_client(fixtures, live, None, settings, no_cache=False)
        if (fixtures is not None or live)
        else None
    )
    try:
        result = build_all(source, out_dir, profile, listener, client=client, budget=budget)
    except IngestError as exc:
        _fail(str(exc))
        return
    except BudgetExceededError as exc:
        _fail(str(exc))
        return

    _print_diagnostics(result.doc)
    if result.elaboration is not None:
        _print_elaboration(result.elaboration)
    console.print(f"[green]wrote[/] {out_dir}: audio.md, study.md, cards.json, manifest.json")
    _print_script_summary(result.script, profile)

    _report_lint(result.lint)
    if not result.lint.ok:
        raise typer.Exit(code=1)


def _profile_and_listener(
    profile_name: str, listener_file: Path | None, settings: Settings
) -> tuple[Profile, Listener]:
    try:
        profile = load_profile(profile_name, settings)
    except FileNotFoundError as exc:
        _fail(str(exc))
        raise
    return profile, load_listener(listener_file, settings)


def _read_script(path: Path) -> Script:
    try:
        return Script.from_json(path.read_bytes())
    except Exception as exc:
        _fail(f"{path} is not a mimem script: {exc}")
        raise


def _find_script(target: Path) -> Path | None:
    """The script in a build directory, or the file itself if it is one."""
    candidate = target / "script.json" if target.is_dir() else target
    return candidate if candidate.exists() and candidate.suffix == ".json" else None


def _script_path(target: Path) -> Path:
    found = _find_script(target)
    if found is None:
        _fail(f"no script at {target}")
        raise typer.Exit(code=1)  # unreachable; _fail raises
    return found


def _sibling_document(target: Path) -> Document | None:
    """The IR next to a script, if the build wrote one -- for showing the source of a span."""
    directory = target if target.is_dir() else target.parent
    candidate = directory / "doc.ir.json"
    if not candidate.exists():
        return None
    try:
        return Document.from_json(candidate.read_bytes())
    except Exception:
        return None


def _load_or_build_registry(
    doc: Document, registry_file: Path | None, ir: Path, listener: Listener
) -> ConceptRegistry:
    candidate = registry_file or ir.with_name(ir.stem.replace(".ir", "") + ".registry.json")
    if candidate.exists():
        try:
            return ConceptRegistry.from_json(candidate.read_bytes())
        except Exception as exc:
            console.print(
                f"[yellow]ignoring unreadable registry[/] {candidate}: {exc}", style="dim"
            )
    console.print(f"[dim]no registry at {candidate}; building one[/]")
    return build_registry(doc, listener)


def _make_client(
    fixtures: Path | None,
    live: bool,
    model: str | None,
    settings: Settings,
    no_cache: bool,
) -> Client:
    """Pick a transport. The default refuses, which is the point.

    A build that starts billing because a flag was forgotten is a bad build, so ``--llm`` is
    explicit and everything else is free.
    """
    client: Client
    if fixtures is not None:
        client = FixtureClient(fixtures)
    elif live:
        from mimem.llm import DEFAULT_MODEL, AnthropicClient

        client = AnthropicClient(model=model or DEFAULT_MODEL)
    else:
        client = NullClient()
    if no_cache or isinstance(client, NullClient):
        return client
    return Cached(inner=client, directory=settings.cache_dir / "llm")


def _print_elaboration(report: object) -> None:
    from mimem.elaborate import ElaborationReport

    if not isinstance(report, ElaborationReport):  # pragma: no cover - defensive
        return
    console.print(f"  {report.summary()}", style="dim")
    for degradation in report.degraded[:5]:
        console.print(f"  [yellow]degraded[/] {degradation}", style="dim")
    if len(report.degraded) > 5:
        console.print(f"  ... and {len(report.degraded) - 5} more", style="dim")
    if report.ledger.calls:
        console.print(f"  {report.ledger.summary()}", style="dim")


def _print_script_summary(script: Script, profile: Profile) -> None:
    minutes = script.est_seconds / 60
    budget = script.budget_seconds / 60
    prompts = sum(1 for b in script.beats() if b.type.value == "prompt")
    console.print(
        f"  {len(script.sections)} sections, {len(script.segments())} segments, "
        f"{len(script.beats())} beats, {prompts} prompts",
        style="dim",
    )
    console.print(
        f"  {minutes:.1f} min against a {budget:.1f} min budget at {profile.wpm:.0f} wpm",
        style="dim",
    )
    scheduled = sum(1 for s in script.schedule if s.exposures > 1)
    console.print(
        f"  {scheduled} concepts come back at least once; {len(script.cards)} cards",
        style="dim",
    )
    for note in script.notes[:3]:
        console.print(f"  [yellow]note[/] {note}", style="dim")
    if script.dropped:
        console.print(f"  {len(script.dropped)} beats cut to fit the budget", style="dim")


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
        where = f"line {v.line}" if v.line else (v.beat_id or "script")
        console.print(f"  [{colour}]{v.rule}[/] {where}: {v.message}", style="dim")
        if v.excerpt:
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
