"""The evaluation harness, and the one property that makes it worth having.

A baseline comparison is only useful if it fails. Most of these tests are therefore about
``compare`` rather than about ``measure``: that it knows which direction each metric is bad in,
that a document vanishing from the corpus is louder than any number moving, and that the
committed baseline is actually reachable from a clean build -- because a baseline that no longer
matches the code is a red build nobody can fix except by overwriting it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mimem.config import Listener, Profile
from mimem.eval import BASELINE, Corpus, Metrics, load_baseline, measure, run
from mimem.eval.harness import documents, table
from mimem.lint import Bundle, lint_all
from mimem.plan import plan
from mimem.render import render


@pytest.fixture
def measured(interphase_doc, study_profile: Profile) -> Metrics:
    from mimem.concepts import build as build_registry

    registry = build_registry(interphase_doc, Listener())
    script = plan(interphase_doc, registry, study_profile, Listener())
    artefacts = render(script, interphase_doc)
    report = lint_all(Bundle(script, interphase_doc, artefacts.audio, artefacts.study))
    return measure(
        interphase_doc, script, report, artefacts.study, study_profile, name="interphase"
    )


def test_a_build_measures_itself(measured: Metrics) -> None:
    assert measured.document == "interphase"
    assert measured.beats > 0
    assert measured.rules_skipped == 0, "a full build should have nothing left unchecked"
    assert 0.0 <= measured.words_retained <= 1.0
    assert 0.0 <= measured.grounded <= 1.0


def test_a_build_compared_with_itself_has_not_regressed(measured: Metrics) -> None:
    assert measured.compare(measured) == []


def test_more_lint_errors_is_a_regression(measured: Metrics) -> None:
    worse = measured.model_copy(update={"lint_errors": measured.lint_errors + 1})
    assert any("lint_errors" in line for line in worse.compare(measured))


def test_fewer_rules_checked_is_a_regression(measured: Metrics) -> None:
    """Deleting a rule makes every other number look the same or better."""
    worse = measured.model_copy(update={"rules_checked": measured.rules_checked - 1})
    assert any("rules_checked" in line for line in worse.compare(measured))


def test_losing_a_value_from_the_written_track_is_a_regression(measured: Metrics) -> None:
    worse = measured.model_copy(update={"values_kept": 0.5})
    assert any("values_kept" in line for line in worse.compare(measured))


def test_a_better_number_is_not_a_regression(measured: Metrics) -> None:
    better = measured.model_copy(update={"concepts_spaced": 1.0, "grounded": 1.0, "lint_errors": 0})
    assert [line for line in better.compare(measured) if "concepts_spaced" in line] == []


def test_small_movements_are_not_regressions(measured: Metrics) -> None:
    """Otherwise the baseline has to be rewritten on every commit, and stops being read."""
    jittered = measured.model_copy(update={"words_retained": measured.words_retained - 0.01})
    assert jittered.compare(measured) == []


def test_a_document_that_stops_building_is_the_loudest_signal() -> None:
    before = Corpus(documents=[Metrics(document="a.pdf"), Metrics(document="b.pdf")])
    after = Corpus(documents=[Metrics(document="a.pdf")])
    assert after.compare(before) == {"b.pdf": ["no longer builds"]}


def test_adding_a_document_is_not_a_regression() -> None:
    before = Corpus(documents=[Metrics(document="a.pdf")])
    after = Corpus(documents=[Metrics(document="a.pdf"), Metrics(document="new.pdf")])
    assert after.compare(before) == {}


def test_the_corpus_is_not_empty() -> None:
    assert documents(), "CI measures nothing if the corpus directory is empty"


def test_the_committed_baseline_covers_the_corpus() -> None:
    baseline = load_baseline(BASELINE)
    assert baseline is not None, f"no baseline at {BASELINE}"
    assert {m.document for m in baseline.documents} == {p.name for p in documents()}


@pytest.mark.slow
def test_the_corpus_still_matches_its_baseline() -> None:
    """The check CI runs, run here too, so a regression fails a local test run as well.

    Slow because it builds every document in the corpus. Everything else in this module is
    arithmetic on a single build.
    """
    baseline = load_baseline(BASELINE)
    assert baseline is not None
    assert run().compare(baseline) == {}


def test_the_table_renders_without_a_terminal(measured: Metrics) -> None:
    rendered = table(Corpus(documents=[measured]))
    assert "interphase" in rendered
    assert len(rendered.splitlines()) == 3  # header, rule, one row


def test_an_empty_corpus_says_so() -> None:
    assert table(Corpus()) == "no documents"


def test_the_baseline_round_trips(tmp_path: Path, measured: Metrics) -> None:
    from mimem.eval import save_baseline

    corpus = Corpus(documents=[measured])
    path = tmp_path / "baseline.json"
    save_baseline(corpus, path)
    assert load_baseline(path) == corpus
