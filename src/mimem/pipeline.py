"""The whole pipeline, in one place, for the two things that need to run it.

``mimem build`` and the assistant server both take a document and produce a programme. They must
run the *same* nine stages in the same order — a second copy of that sequence would drift the
first time a stage moved, and the failure would be silent and specific to whichever caller nobody
was testing.

So the sequence lives here and the callers differ only in what they do with the result: the CLI
prints it, the server summarises it for a conversation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mimem.clean import clean
from mimem.concepts import build as build_registry
from mimem.config import Listener, Profile
from mimem.elaborate import ElaborationReport, elaborate
from mimem.ingest import load
from mimem.ingest.crops import render_figures
from mimem.ir import ConceptRegistry, Document, Script
from mimem.lint import Bundle, LintReport, lint_all
from mimem.llm.client import Client
from mimem.plan import plan
from mimem.render import Artefacts, render
from mimem.triage import drop_report, triage

#: What a build leaves on disk, beyond the four artefacts. Every intermediate stage is kept so
#: that you can stop, edit the JSON by hand, and resume (PLAN section 1).
INTERMEDIATE = ("doc.ir.json", "registry.json", "script.json", "drop-report.md")


@dataclass
class BuildResult:
    """Everything a build produced, before anybody decides how to report it."""

    out_dir: Path
    doc: Document
    registry: ConceptRegistry
    script: Script
    artefacts: Artefacts
    lint: LintReport
    elaboration: ElaborationReport | None = None
    written: list[Path] = field(default_factory=list)

    @property
    def minutes(self) -> float:
        return self.script.est_seconds / 60.0

    @property
    def budget_minutes(self) -> float:
        return self.script.budget_seconds / 60.0

    def summary(self) -> dict[str, object]:
        """The shape of a build, small enough to put in a conversation."""
        prompts = sum(1 for b in self.script.beats() if b.type.value == "prompt")
        returning = sum(1 for s in self.script.schedule if s.exposures > 1)
        return {
            "title": self.doc.source.title or "untitled",
            "authors": self.doc.source.authors[:6],
            "minutes": round(self.minutes, 1),
            "budget_minutes": round(self.budget_minutes, 1),
            "sections": len(self.script.sections),
            "segments": len(self.script.segments()),
            "beats": len(self.script.beats()),
            "questions": prompts,
            "cards": len(self.script.cards),
            "concepts": len(self.script.registry),
            "concepts_returning": returning,
            "words_retained_pct": _retention(self.doc),
            "lint_errors": len(self.lint.errors),
            "lint_warnings": len(self.lint.warnings),
            "notes": self.script.notes[:5],
        }


def _retention(doc: Document) -> int:
    """How much of the document survived triage, as a percentage of its words."""
    from mimem.triage.rules import retained

    total = doc.word_count
    kept = sum(len(b.text.split()) for b in retained(doc))
    return round(100 * kept / total) if total else 0


def build_all(
    source: Path,
    out_dir: Path,
    profile: Profile,
    listener: Listener | None = None,
    *,
    client: Client | None = None,
    budget: float | None = None,
    model: str | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> BuildResult:
    """Stages 1 through 9: a source document to a checked programme on disk.

    ``client`` is stage 6. Leave it ``None`` and the elaboration layer is skipped entirely, which
    is the default everywhere: no model is called unless somebody asks for one.
    """
    listener = listener or Listener()
    doc = triage(clean(load(source)))

    registry = build_registry(doc, listener)

    # Crops first. study.md links them, and stage 6 *sends* them -- a figure cannot be described
    # from a picture that has not been rendered yet. Failing to render one costs a picture and
    # nothing else; the audio track never mentions a file.
    out_dir.mkdir(parents=True, exist_ok=True)
    render_figures(doc, out_dir)

    elaboration = None
    if client is not None:
        elaboration = elaborate(
            doc,
            registry,
            profile,
            listener,
            client,
            budget=budget,
            out_dir=out_dir,
            model=model,
            progress=progress,
        )

    script = plan(doc, registry, profile, listener)
    artefacts = render(script, doc, elaboration)

    (out_dir / "doc.ir.json").write_text(doc.to_json(), encoding="utf-8")
    (out_dir / "registry.json").write_text(registry.to_json(), encoding="utf-8")
    (out_dir / "script.json").write_text(script.to_json(), encoding="utf-8")
    (out_dir / "drop-report.md").write_text(drop_report(doc), encoding="utf-8")
    written = artefacts.write(out_dir)

    return BuildResult(
        out_dir=out_dir,
        doc=doc,
        registry=registry,
        script=script,
        artefacts=artefacts,
        lint=lint_all(Bundle(script, doc, artefacts.audio, artefacts.study), profile),
        elaboration=elaboration,
        written=[*written, *(out_dir / name for name in INTERMEDIATE)],
    )


def replan(out_dir: Path, profile: Profile, listener: Listener | None = None) -> BuildResult:
    """Re-run stages 7 to 9 over the documents already on disk.

    What you want after editing ``registry.json`` by hand, or after the elaboration layer has
    filled it in: the expensive and non-deterministic parts are already done.
    """
    doc = Document.from_json((out_dir / "doc.ir.json").read_bytes())
    registry = ConceptRegistry.from_json((out_dir / "registry.json").read_bytes())
    script = plan(doc, registry, profile, listener)
    render_figures(doc, out_dir)
    # No elaboration report: `replan` re-runs stages 7 to 9 and stage 6 is not among them, so
    # there is nothing new to record. The manifest keeps the shape it had without the section
    # rather than claiming an empty run.
    artefacts = render(script, doc)

    (out_dir / "script.json").write_text(script.to_json(), encoding="utf-8")
    written = artefacts.write(out_dir)

    return BuildResult(
        out_dir=out_dir,
        doc=doc,
        registry=registry,
        script=script,
        artefacts=artefacts,
        lint=lint_all(Bundle(script, doc, artefacts.audio, artefacts.study), profile),
        written=written,
    )
