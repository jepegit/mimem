"""Command line interface.

Every stage is a file-to-file transform, so that you can stop after any of them, edit the
intermediate JSON by hand, and resume (PLAN section 1). ``inspect`` is not a debugging
afterthought -- it is how you find out that ingestion quietly ate the methods section.
"""

from __future__ import annotations

import contextlib
import io
import sys
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
from mimem.eval import BASELINE
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
from mimem.lint import Bundle, LintReport, Severity
from mimem.lint import lint as run_lint
from mimem.lint import lint_all as run_lint_all
from mimem.lint import lint_script as run_lint_script
from mimem.llm import Cached, Client, FixtureClient, NullClient
from mimem.llm.cost import BudgetExceededError
from mimem.pipeline import build_all
from mimem.plan import plan as run_plan
from mimem.render import narrate as run_narrate
from mimem.render import render as run_render
from mimem.render import render_audio
from mimem.speak import ENGINES, AudioError, EngineError, EngineOptions, SpeechChunk, Synthesis
from mimem.speak import create as create_engine
from mimem.speak import speech_chunks as run_speech_chunks
from mimem.speak import synthesize as run_synthesize
from mimem.triage import drop_report
from mimem.triage import triage as run_triage

app = typer.Typer(
    name="mimem",
    help="Convert your library into audio that is designed for remembering.",
    no_args_is_help=True,
    add_completion=False,
)


def _speakable_console(*, stderr: bool = False) -> Console:
    """A console that cannot be killed by the text it is asked to print.

    Windows terminals still default to cp1252, which has no code point for most of what a
    scientific PDF contains. A single U+2206 in a ninety-eight page review was enough to end
    ``mimem build`` in a ``UnicodeEncodeError`` traceback -- and the character was in a *lint
    violation*, so the crash landed exactly where the tool was trying to say what was wrong
    with the document. The artefacts had already been written; only the report died.

    Replacing the unencodable character costs a "?" in a terminal that could not have shown the
    real one anyway. Set on the CLI's own consoles rather than by reconfiguring ``sys.stdout``,
    because the MCP server shares this process family and nothing may touch its stdout.
    """
    stream = sys.stderr if stderr else sys.stdout
    # Not every stdout is a real one: pytest and the notebook capture replace it with objects
    # that have no encoding to reconfigure, and there is nothing to fix in those.
    if isinstance(stream, io.TextIOWrapper):
        with contextlib.suppress(ValueError, OSError):
            stream.reconfigure(errors="replace")
    return Console(stderr=stderr)


console = _speakable_console()
err = _speakable_console(stderr=True)


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

    How much it can check depends on what it is given, and it always says which. A build
    directory has everything: the narration against the speakability rules, the plan against the
    structure, retrieval and spacing rules, and the artefacts against each other. A bare
    ``script.json`` cannot answer the cross-artefact rules, and a bare ``audio.md`` can only
    answer the first family.
    """
    settings = Settings()
    profile, _ = _profile_and_listener(profile_name, None, settings)

    script_file = _find_script(target)
    if script_file is not None:
        script = _read_script(script_file)
        audio_file = target / "audio.md" if target.is_dir() else None
        audio = (
            audio_file.read_text(encoding="utf-8")
            if audio_file and audio_file.exists()
            else render_audio(script)
        )
        study_file = target / "study.md" if target.is_dir() else None
        doc = _sibling_document(target)
        if doc is not None and study_file is not None and study_file.exists():
            report = run_lint_all(
                Bundle(script, doc, audio, study_file.read_text(encoding="utf-8")), profile
            )
        else:
            report = run_lint_script(script, audio, profile)
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
    provider: Annotated[
        str, typer.Option("--provider", help=f"with --llm: {', '.join(PROVIDERS)}")
    ] = "anthropic",
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="for --provider openai/local")
    ] = None,
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

    client = _make_client(fixtures, live, model, settings, no_cache, provider, base_url)
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
    provider: Annotated[
        str, typer.Option("--provider", help=f"with --llm: {', '.join(PROVIDERS)}")
    ] = "anthropic",
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="for --provider openai/local")
    ] = None,
    speak_with: Annotated[
        str | None,
        typer.Option("--speak", help=f"also synthesise audio; one of: {', '.join(ENGINES)}"),
    ] = None,
    voice: Annotated[str | None, typer.Option("--voice", help="engine's own voice name")] = None,
) -> None:
    """The whole pipeline: source document to a listenable, checkable programme.

    Stage 6 is off by default. With ``--local`` you get the paper said in a way you can follow,
    with the questions and the spacing that make it stick; with ``--llm`` you also get the
    glosses, the concrete anchors and the analogies, and a bill.

    With ``--speak`` it goes all the way to a WAV file, which is the whole of milestone M7:
    one command from a PDF to something you can play.
    """
    settings = Settings()
    profile, listener = _profile_and_listener(profile_name, listener_file, settings)

    # The nine stages live in `mimem.pipeline`, shared with the assistant server: two copies of
    # that sequence would drift the first time a stage moved.
    client = (
        _make_client(fixtures, live, None, settings, False, provider, base_url)
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

    if speak_with is not None:
        # After the lint report, and only if it passed. Synthesising a script that broke a rule
        # would spend time or money producing audio with a known defect in it, and the whole
        # point of the linter's non-zero exit is that a bad script does not get used quietly.
        if not result.lint.ok:
            console.print(
                "[yellow]not synthesising[/]: the script has lint errors. "
                "Fix them, or run `mimem speak` on it deliberately.",
            )
        else:
            try:
                engine = create_engine(speak_with, EngineOptions(voice=voice))
                synthesis = run_synthesize(result.script, engine, out_dir=out_dir)
            except (EngineError, AudioError, ValueError) as exc:
                _fail(str(exc))
                return
            for path in synthesis.write(out_dir):
                console.print(f"[green]wrote[/] {path}")
            _print_synthesis(synthesis)

    if not result.lint.ok:
        raise typer.Exit(code=1)


@app.command()
def speak(
    target: Annotated[Path, typer.Argument(help="script JSON, or a directory containing one")],
    engine_name: Annotated[
        str, typer.Option("--engine", "-e", help=f"one of: {', '.join(ENGINES)}")
    ] = "silent",
    out_dir: Annotated[
        Path | None, typer.Option("--out", "-o", help="where to write; defaults beside the script")
    ] = None,
    voice: Annotated[str | None, typer.Option("--voice", help="engine's own voice name")] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="piper voice file, or TTS model")
    ] = None,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="for --engine openai; any compatible server")
    ] = None,
    rate: Annotated[int, typer.Option("--rate", help="SAPI speaking rate, -10 to 10")] = 0,
    use_cache: Annotated[
        bool, typer.Option("--cache/--no-cache", help="reuse audio for unchanged beats")
    ] = True,
) -> None:
    """Stage 9: the script as a playable file, with the pauses actually in it.

    The silences that carry retrieval time are inserted here rather than requested from the
    engine, so every engine produces the same pauses in the same places and only the voice
    differs (rule TTS-05).

    Beats are cached by content, so fixing one sentence re-synthesises one beat.
    """
    script = _read_script(_script_path(target))
    destination = out_dir or (target if target.is_dir() else target.parent)
    try:
        engine = create_engine(
            engine_name,
            EngineOptions(voice=voice, model=model, rate=rate, base_url=base_url),
        )
    except EngineError as exc:
        _fail(str(exc))
        return

    chunks = len(run_speech_chunks(script))
    console.print(f"synthesising [bold]{chunks}[/] beats with [bold]{engine.name}[/]")
    with console.status("speaking...") as status:

        def tick(index: int, total: int, chunk: SpeechChunk, reused: bool) -> None:
            mark = "cached" if reused else "spoke"
            status.update(f"{mark} {index + 1}/{total}  {chunk.text[:60]}")

        try:
            result = run_synthesize(
                script, engine, out_dir=destination, use_cache=use_cache, progress=tick
            )
        except (EngineError, AudioError) as exc:
            _fail(str(exc))
            return
        except ValueError as exc:
            _fail(str(exc))
            return

    for path in result.write(destination):
        console.print(f"[green]wrote[/] {path}")
    _print_synthesis(result)


@app.command("compare")
def compare_paths(
    source: Annotated[Path, typer.Argument(help="the document to build twice")],
    out_dir: Annotated[Path, typer.Option("--out", "-o")] = Path("out/compare"),
    fixtures: Annotated[
        Path | None, typer.Option("--fixtures", help="replay a recorded run instead of paying")
    ] = None,
    provider: Annotated[
        str, typer.Option("--provider", help=f"one of: {', '.join(PROVIDERS)}")
    ] = "anthropic",
    model: Annotated[str | None, typer.Option("--model")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url")] = None,
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
    budget: Annotated[float | None, typer.Option("--budget", help="hard cap in US dollars")] = None,
    as_json_output: Annotated[bool, typer.Option("--json", help="print the comparison as JSON")] = (
        False
    ),
) -> None:
    """Build one document twice, with and without a model, and say what the model changed.

    This project's argument is that structure matters more than fluency, which is a claim about
    what a model is worth here. This is how to check it: the deterministic build is the control,
    the assisted build is the treatment, and the difference is what you paid for.

    ``--fixtures`` compares against a recorded run, so the comparison is free and repeatable
    after one `mimem record`.
    """
    from mimem.eval.compare import compare as run_compare

    settings = Settings()
    profile, listener = _profile_and_listener(profile_name, listener_file, settings)
    client = (
        FixtureClient(fixtures)
        if fixtures is not None
        else _make_client(None, True, model, settings, False, provider, base_url)
    )

    try:
        result = run_compare(source, out_dir, profile, listener, client, budget=budget)
    except IngestError as exc:
        _fail(str(exc))
        return
    except BudgetExceededError as exc:
        _fail(str(exc))
        return

    if as_json_output:
        console.print_json(result.to_json())
        return

    console.print(f"[bold]{result.document}[/]  local vs. model\n")
    table = Table("metric", "local", "with model", "change")
    for change in result.changes():
        arrow = {True: "[green]better[/]", False: "[red]worse[/]", None: ""}[change.better]
        table.add_row(
            change.name,
            f"{change.local:g}",
            f"{change.with_model:g}",
            f"{change.delta:+g} {arrow}".strip(),
        )
    console.print(table)

    if result.added:
        added = ", ".join(f"{n} {task}" for task, n in sorted(result.added.items()))
        console.print(f"the model wrote: [bold]{added}[/]")
    if result.absences:
        for kind, count in sorted(result.absences.items()):
            console.print(f"  {count} x {kind}", style="dim")
    console.print(f"cost: [bold]${result.dollars:.4f}[/] over {result.calls} calls")
    per = result.cost_per_gloss
    if per is not None:
        console.print(f"  ${per:.4f} per term defined", style="dim")


@app.command()
def record(
    source: Annotated[Path, typer.Argument(help="the document to run against a live model")],
    out_dir: Annotated[Path, typer.Option("--out", "-o", help="where the fixtures go")] = Path(
        "fixtures"
    ),
    provider: Annotated[
        str, typer.Option("--provider", help=f"one of: {', '.join(PROVIDERS)}")
    ] = "anthropic",
    model: Annotated[str | None, typer.Option("--model")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url")] = None,
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    listener_file: Annotated[Path | None, typer.Option("--listener")] = None,
    budget: Annotated[float | None, typer.Option("--budget", help="hard cap in US dollars")] = None,
) -> None:
    """Run stage 6 against a live model once, and keep every answer as a fixture.

    One paid run becomes a set anyone can replay with ``--fixtures`` for nothing, forever. That
    is how the worked example in the docs stays reproducible, how the tests stay free, and how
    you compare two changes to the *rest* of the pipeline without the model moving underneath
    the comparison.

    **This one always bills.** Every other command defaults to spending nothing; this is the
    exception, and it says so rather than hiding behind a flag.
    """
    settings = Settings()
    profile, listener = _profile_and_listener(profile_name, listener_file, settings)
    try:
        doc = run_clean(run_ingest(source))
    except IngestError as exc:
        _fail(str(exc))
        return
    doc = run_triage(doc)
    registry = build_registry(doc, listener)

    from mimem.llm import RecordingClient

    inner = _live_client(provider, model, base_url)
    client = RecordingClient(inner=inner, directory=out_dir)
    console.print(f"recording [bold]{provider}[/] answers into {out_dir}")
    try:
        report = run_elaborate(doc, registry, profile, listener, client, budget=budget)
    except BudgetExceededError as exc:
        _fail(str(exc))
        return

    written = sorted(out_dir.glob("*.json"))
    console.print(f"[green]wrote[/] {len(written)} fixtures to {out_dir}")
    console.print(f"  replay with: mimem build {source} --fixtures {out_dir}", style="dim")
    _print_elaboration(report)


@app.command()
def doctor(
    live: Annotated[
        bool,
        typer.Option("--live", help="actually call each configured provider, not just check it"),
    ] = False,
    model: Annotated[str | None, typer.Option("--model", help="model to use for --live")] = None,
) -> None:
    """What AI is reachable from here, and the exact next thing to type for what is not.

    Nothing in mimem requires a model: run this on a machine with no keys and it will say so
    and tell you what still works. That is the point of it. The alternative -- and what
    happened before this command existed -- is meeting each absence separately as its own
    confusing error and concluding the tool is broken.

    ``--live`` sends one tiny structured request to each configured provider, because "the key
    is set" and "the key works" are different claims.
    """
    from mimem.llm.reach import State, probe, survey

    checks = survey()
    if live:
        with console.status("calling each configured provider..."):
            checks = [probe(c, model=model) for c in checks]

    colour = {
        State.READY: "green",
        State.CONFIGURED: "cyan",
        State.MISSING_KEY: "yellow",
        State.NOT_INSTALLED: "yellow",
        State.UNREACHABLE: "red",
        State.FAILED: "red",
    }
    group = ""
    for check in checks:
        if check.group != group:
            group = check.group
            console.print(f"\n[bold]{group}[/]")
        # Pad the plain value before wrapping it in markup: the tags are zero-width on screen
        # and full-width to `format`, so padding the marked-up string misaligns every row.
        state = f"[{colour[check.state]}]{check.state.value:<14}[/]"
        console.print(f"  {check.name:<11}{state}{check.detail}", highlight=False)
        if not check.ok and check.fix:
            console.print(f"  {'':<11}[dim]-> {check.fix}[/]", highlight=False)

    if not live:
        console.print(
            "\n[dim]Configuration only. Run `mimem doctor --live` to make one real request "
            "to each provider.[/]"
        )
    usable = [c for c in checks if c.group == "text generation" and c.ok]
    if len(usable) == 1:
        console.print(
            "\nThe assistant is your only route to a model right now, and it needs no key: "
            "install the Claude Desktop extension, or see docs/ai/no-key.md for everything "
            "that works without one."
        )


@app.command()
def voices(
    engine_name: Annotated[
        str, typer.Option("--engine", "-e", help=f"one of: {', '.join(ENGINES)}")
    ] = "sapi",
) -> None:
    """What this engine can sound like."""
    try:
        engine = create_engine(engine_name)
        found = engine.voices()
    except EngineError as exc:
        _fail(str(exc))
        return
    if not found:
        console.print(
            f"{engine_name} cannot list its voices; pass one with --voice or --model", style="dim"
        )
        return
    table = Table("voice", "name", "locale")
    for v in found:
        table.add_row(v.id, v.name, v.locale)
    console.print(table)


@app.command("eval")
def evaluate(
    corpus: Annotated[
        Path | None, typer.Option("--corpus", help="directory of documents to measure")
    ] = None,
    profile_name: Annotated[str, typer.Option("--profile", "-p")] = "study",
    update: Annotated[
        bool, typer.Option("--update", help="write the result as the new committed baseline")
    ] = False,
    baseline_path: Annotated[
        Path | None, typer.Option("--baseline", help="baseline to compare against")
    ] = None,
    as_json_output: Annotated[bool, typer.Option("--json", help="print metrics as JSON")] = False,
) -> None:
    """Measure the corpus, and compare it against the committed baseline.

    Exits non-zero on a regression, which is what makes it useful in CI: the linter would still
    be green, because none of the ways this system silently gets worse are broken output.

    ``--update`` writes the new numbers down. That is the only way to make a regression pass,
    and it puts the worse number in the diff where a reviewer has to look at it.
    """
    from mimem.eval import as_json, load_baseline, run, save_baseline, table

    profile, _ = _profile_and_listener(profile_name, None, Settings())
    paths = sorted(corpus.iterdir()) if corpus is not None else None
    measured = run(paths, profile)
    if not measured.documents:
        _fail("no documents to measure")
        return

    console.print(as_json(measured) if as_json_output else table(measured))

    path = baseline_path or BASELINE
    if update:
        save_baseline(measured, path)
        console.print(f"[green]baseline written[/] {path}")
        return

    previous = load_baseline(path)
    if previous is None:
        console.print(f"[yellow]no baseline at {path}[/]; run with --update to write one")
        return

    regressions = measured.compare(previous)
    if not regressions:
        console.print(f"[green]no regressions[/] against {path}")
        return
    for document, lines in regressions.items():
        console.print(f"[red]{document}[/]")
        for line in lines:
            console.print(f"  {line}")
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


#: What ``--provider`` takes. Four names, three implementations: ``openai`` and ``local`` are
#: the same adapter with different defaults, because the difference between a hosted server and
#: one on your laptop is a base URL.
PROVIDERS = ("anthropic", "openai", "local")


def _live_client(provider: str, model: str | None, base_url: str | None) -> Client:
    """The one transport that can cost money, chosen explicitly."""
    if provider == "anthropic":
        from mimem.llm import DEFAULT_MODEL, AnthropicClient

        return AnthropicClient(model=model or DEFAULT_MODEL)

    from mimem.llm.openai import LOCAL_BASE_URLS, OpenAICompatibleClient

    if provider == "openai":
        client = OpenAICompatibleClient(model=model or "gpt-4o-mini")
        if base_url:
            client.base_url = base_url.rstrip("/")
        return client

    if provider == "local":
        from mimem.llm.reach import port_open

        # Find the server the user has already started rather than asking them which one it
        # is: `mimem doctor` reports the same set, so the two agree about what "local" means.
        url = base_url or next((u for u in LOCAL_BASE_URLS.values() if port_open(u)), None)
        if url is None:
            _fail(
                "no local model server is listening. Start one (`ollama serve`), or pass "
                "--base-url. `mimem doctor` lists the ports that were checked."
            )
        return OpenAICompatibleClient(base_url=str(url), model=model or "llama3.2")

    _fail(f"unknown provider {provider!r}; available: {', '.join(PROVIDERS)}")
    raise AssertionError("unreachable")  # pragma: no cover - _fail exits


def _make_client(
    fixtures: Path | None,
    live: bool,
    model: str | None,
    settings: Settings,
    no_cache: bool,
    provider: str = "anthropic",
    base_url: str | None = None,
) -> Client:
    """Pick a transport. The default refuses, which is the point.

    A build that starts billing because a flag was forgotten is a bad build, so ``--llm`` is
    explicit and everything else is free.
    """
    client: Client
    if fixtures is not None:
        client = FixtureClient(fixtures)
    elif live:
        client = _live_client(provider, model, base_url)
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


def _print_synthesis(result: Synthesis) -> None:
    """What the audio actually turned out to be, against what was predicted.

    The drift line is the interesting one. Every duration in this project up to now has been a
    word count divided by a words-per-minute figure from the profile; this is the first time
    the pipeline can say what the programme really runs to, and whether ``SEG-01``'s segment
    bounds were being checked against a number that bears any relation to speech.
    """
    minutes = result.seconds / 60
    console.print(
        f"  [bold]{minutes:.1f} min[/] of audio, {result.synthesised} beats synthesised, "
        f"{result.reused} reused from cache",
        style="dim",
    )
    predicted = result.estimated_seconds / 60
    drift = result.drift
    direction = "over" if drift >= 0 else "under"
    share = abs(drift) / result.estimated_seconds * 100 if result.estimated_seconds else 0.0
    console.print(
        f"  predicted {predicted:.1f} min, so {abs(drift) / 60:.1f} min {direction} ({share:.0f}%)",
        style="dim",
    )


def _report_lint(report: LintReport, examples: int = 3) -> None:
    """Print a lint report: counts first, then a few examples of each rule."""
    if report.ok and not report.warnings:
        console.print(f"[green]lint clean[/] ({len(report.checked_rules)} rules)")
        _report_skipped(report)
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
    _report_skipped(report)


def _report_skipped(report: LintReport) -> None:
    """A clean report that skipped rules is not the same as a clean report, and must not read
    like one. Printed in both branches, because the branch it is easiest to misread is the
    green one."""
    for line in report.skipped:
        console.print(f"  [yellow]not checked[/] {line}", style="dim")


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
