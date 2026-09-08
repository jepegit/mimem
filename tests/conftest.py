"""Shared fixtures.

The synthetic paper is rebuilt from ``make_paper_pdf.py`` when reportlab is available, so the
tests always exercise the generator they document. The committed copy in ``fixtures/docs`` is
the fallback (and what you open by hand when a test fails and you want to see the page).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "docs"
COMMITTED_PAPER = FIXTURE_DIR / "synthetic-paper.pdf"

MARKDOWN_SOURCE = """\
# On Interphase Repair

Some background prose that runs across
two source lines but is one paragraph.

## 2. Methods

- first bullet
- second bullet

Another paragraph, with a value of 0.0837 % per cycle. It has two sentences.
"""


@pytest.fixture(scope="session")
def paper_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The synthetic two-column paper."""
    try:
        from make_paper_pdf import build  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - reportlab is a dev dependency
        if not COMMITTED_PAPER.exists():
            pytest.skip("no synthetic paper fixture and reportlab is not installed")
        return COMMITTED_PAPER
    return build(tmp_path_factory.mktemp("docs") / "synthetic-paper.pdf")


@pytest.fixture(scope="session")
def paper_doc(paper_pdf: Path):
    """The synthetic paper after ingest + clean. Session-scoped: treat as read-only."""
    from mimem.clean import clean
    from mimem.ingest import load

    return clean(load(paper_pdf))


@pytest.fixture
def markdown_file(tmp_path: Path) -> Path:
    path = tmp_path / "note.md"
    path.write_text(MARKDOWN_SOURCE, encoding="utf-8")
    return path


# -- the worked example ----------------------------------------------------------------------

from worked_example import ANSWERS, _doc  # noqa: E402  (tests/fixtures is on sys.path)

from mimem.config import Profile, load_profile  # noqa: E402
from mimem.ir import Document  # noqa: E402


@pytest.fixture
def sample_doc() -> Document:
    """The worked example's source paragraph, triaged and ready for stage 6."""
    return _doc()


@pytest.fixture
def study() -> Profile:
    return load_profile("study")


@pytest.fixture
def scripted_answers() -> dict[str, list[dict[str, object]]]:
    """What the target rendering says, in the shape each task returns it."""
    return {task: [dict(answer) for answer in answers] for task, answers in ANSWERS.items()}
