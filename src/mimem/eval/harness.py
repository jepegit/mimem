"""Run the metrics over a corpus, and hold the result against a committed baseline.

The linter answers "is this output broken". This answers "is this output *worse than it was*",
which is a different question and the one that a design of ninety interacting rules will
actually fail at. Nothing in mimem breaks loudly: a scorer that drifts, a scheduler that finds
one fewer slot, a triage rule that eats an extra paragraph -- each of those produces a programme
that lints clean and teaches less.

So the baseline is committed, in ``tests/fixtures/eval/baseline.json``, and CI rebuilds the
corpus and compares. A pull request that lowers a number has to say so in its diff, which turns
"did this get worse" from a judgement call into a line of review.

Regenerating the baseline is deliberately a separate command (``mimem eval --update``): the only
way to make CI green after a real regression is to write the worse number down where a reviewer
can see it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path

from mimem.config import Listener, Profile
from mimem.eval.metrics import Corpus, measure
from mimem.pipeline import build_all

#: Where the committed baseline lives, relative to the repository root.
BASELINE = Path("tests/fixtures/eval/baseline.json")

#: The corpus. Small on purpose: these run on every pull request, on four platform/version
#: combinations, and a corpus nobody waits for is a corpus that gets disabled.
CORPUS = Path("tests/fixtures/docs")


def documents(corpus: Path = CORPUS) -> list[Path]:
    """Every document in the corpus, in a stable order."""
    return sorted(
        p for p in corpus.iterdir() if p.suffix.lower() in {".pdf", ".md", ".txt", ".epub"}
    )


def run(
    paths: Iterable[Path] | None = None,
    profile: Profile | None = None,
    listener: Listener | None = None,
) -> Corpus:
    """Build every document in the corpus and measure the result."""
    profile = profile or Profile(name="study")
    out = Corpus()
    for path in paths if paths is not None else documents():
        with tempfile.TemporaryDirectory() as tmp:
            result = build_all(path, Path(tmp), profile, listener)
            out.documents.append(
                measure(
                    result.doc,
                    result.script,
                    result.lint,
                    result.artefacts.study,
                    profile,
                    name=path.name,
                )
            )
    return out


def load_baseline(path: Path = BASELINE) -> Corpus | None:
    """The committed baseline, or ``None`` if there is not one yet."""
    if not path.exists():
        return None
    return Corpus.model_validate_json(path.read_text(encoding="utf-8"))


def save_baseline(corpus: Corpus, path: Path = BASELINE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corpus.model_dump_json(indent=2) + "\n", encoding="utf-8")


def table(corpus: Corpus) -> str:
    """The corpus as a table, for a terminal or a pull-request comment."""
    if not corpus.documents:
        return "no documents"
    columns = (
        ("document", lambda m: m.document[:34]),
        ("min", lambda m: f"{m.minutes:.0f}"),
        ("used", lambda m: f"{m.budget_used:.2f}"),
        ("cards", lambda m: str(m.cards)),
        ("q/min", lambda m: f"{m.prompts_per_minute:.2f}"),
        ("gloss", lambda m: f"{m.gloss_coverage:.2f}"),
        ("spaced", lambda m: f"{m.concepts_spaced:.2f}"),
        ("expand", lambda m: f"{m.intervals_expanding:.2f}"),
        ("ground", lambda m: f"{m.grounded:.2f}"),
        ("values", lambda m: f"{m.values_kept:.2f}"),
        ("kept", lambda m: f"{m.words_retained:.2f}"),
        ("err", lambda m: str(m.lint_errors)),
        ("warn", lambda m: str(m.lint_warnings)),
    )
    rows = [[name for name, _ in columns]]
    rows.extend([render(m) for _, render in columns] for m in corpus.documents)
    widths = [max(len(row[i]) for row in rows) for i in range(len(columns))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)) for row in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(line.rstrip() for line in lines)


def as_json(corpus: Corpus) -> str:
    return corpus.model_dump_json(indent=2)
