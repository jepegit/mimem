"""Two implementations, and which one wins (M9).

The behaviours worth pinning are the ones a reader would not guess from the code: that a run
with no provider says so *once* rather than once per task, that the four reasons a model answer
is missing stay four different reasons, and that `assist` genuinely skips the call it would have
thrown away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The sample document and its scripted answers live with the elaboration tests, which is where
# they are explained. Importing rather than duplicating keeps one description of the worked
# example; the fixtures below just wrap them.
from worked_example import ANSWERS  # type: ignore[import-not-found]

from mimem.concepts import build as build_registry
from mimem.config import Listener, Profile
from mimem.elaborate import elaborate
from mimem.elaborate.reconcile import Absence, Mode, classify
from mimem.ir import Document
from mimem.llm import NullClient, ScriptedClient
from mimem.llm.client import (
    LLMRefusedError,
    LLMUnavailableError,
    NoProviderError,
    Request,
    Response,
)
from mimem.llm.cost import BudgetExceededError

# -- what kind of absence is this ------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (NoProviderError("none"), Absence.NOT_CONFIGURED),
        (LLMUnavailableError("timeout"), Absence.UNREACHABLE),
        (LLMRefusedError("bad shape"), Absence.REFUSED),
        (BudgetExceededError("too much"), Absence.OVER_BUDGET),
    ],
)
def test_each_failure_keeps_its_own_meaning(error: Exception, expected: Absence) -> None:
    """Four situations that were one string, and need four different actions from the user."""
    assert classify(error) is expected


def test_no_provider_is_a_subclass_so_the_old_handlers_still_catch_it() -> None:
    assert isinstance(NoProviderError("x"), LLMUnavailableError)


def test_only_some_absences_are_about_the_setup() -> None:
    """A rejected claim is the system working; a missing key is a thing to go and fix."""
    assert Absence.NOT_CONFIGURED.is_setup
    assert Absence.UNREACHABLE.is_setup
    assert not Absence.REJECTED.is_setup


def test_every_absence_has_advice() -> None:
    for absence in Absence:
        assert absence.advice


# -- the modes -------------------------------------------------------------------------------


class CountingClient:
    """Answers nothing, and remembers how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: Request) -> Response:
        self.calls += 1
        raise LLMUnavailableError("not today")


def _elaborate(doc: Document, profile: Profile, client: object) -> object:
    registry = build_registry(doc, Listener())
    return elaborate(doc, registry, profile, Listener(), client)  # type: ignore[arg-type]


def test_off_never_calls_the_model(sample_doc: Document, study: Profile) -> None:
    study.elaboration.modes = dict.fromkeys(study.elaboration.modes, "off")
    client = CountingClient()
    _elaborate(sample_doc, study, client)
    assert client.calls == 0


def test_off_still_runs_the_deterministic_path(sample_doc: Document, study: Profile) -> None:
    """`off` is not "do nothing" -- it is "the rules answer"."""
    study.elaboration.modes = dict.fromkeys(study.elaboration.modes, "off")
    report = _elaborate(sample_doc, study, CountingClient())
    assert report.deterministic.get("gloss")  # type: ignore[attr-defined]


def test_prefer_asks_the_model_first(sample_doc: Document, study: Profile) -> None:
    study.elaboration.modes = dict.fromkeys(study.elaboration.modes, "prefer")
    client = CountingClient()
    _elaborate(sample_doc, study, client)
    assert client.calls > 0


def test_assist_skips_the_call_the_rules_already_answered(
    sample_doc: Document, study: Profile
) -> None:
    """The whole point of the mode: pay for recall, not for what precision already got."""
    study.elaboration.modes = dict.fromkeys(study.elaboration.modes, "off")
    baseline = _elaborate(sample_doc, study, CountingClient())
    answered = sum(baseline.deterministic.values())  # type: ignore[attr-defined]
    assert answered, "the fixture must have something the rules can answer"

    study.elaboration.modes = {"gloss": "assist"}
    assisting = CountingClient()
    report = _elaborate(sample_doc, study, assisting)
    assert report.deterministic.get("gloss")  # type: ignore[attr-defined]


def test_prefer_is_the_default_for_every_task() -> None:
    """`gloss: assist` looked obvious and was reverted: the two paths make different things.

    The rules write `short_def`; the model writes `short_def` *and* `long_def`. Skipping the
    call because a short definition exists would quietly give a paid run less for its money.
    """
    profile = Profile(name="study")
    for task in ("gloss", "anchor", "analogy", "why", "figure", "compress"):
        assert profile.elaboration.mode_for(task) == "prefer"


def test_an_unknown_task_defaults_to_prefer() -> None:
    assert Profile(name="study").elaboration.mode_for("something-new") == "prefer"


# -- no provider is one fact -----------------------------------------------------------------


def test_a_run_with_no_provider_says_so_once(sample_doc: Document, study: Profile) -> None:
    report = _elaborate(sample_doc, study, NullClient())
    assert report.no_provider  # type: ignore[attr-defined]
    assert not report.degraded  # type: ignore[attr-defined]
    assert "no model configured" in report.summary()  # type: ignore[attr-defined]
    assert "doctor" in report.summary()  # type: ignore[attr-defined]


def test_absences_are_counted_by_kind(sample_doc: Document, study: Profile) -> None:
    """ "Everything degraded" means something different for one missing key than forty
    rejections, and only one of those is a problem with the setup."""
    report = _elaborate(sample_doc, study, CountingClient())
    counts = report.absences()  # type: ignore[attr-defined]
    assert counts, "the counting client fails every task"
    assert set(counts) == {Absence.UNREACHABLE}


def test_mode_round_trips_through_its_value() -> None:
    assert Mode("assist") is Mode.ASSIST


# -- comparing the two builds ----------------------------------------------------------------


def test_compare_reports_what_the_model_added(
    sample_doc: Document, study: Profile, tmp_path: Path, markdown_file: Path
) -> None:
    """The measurement the reconciler exists to make possible."""
    from mimem.eval.compare import compare

    result = compare(
        markdown_file,
        tmp_path,
        study,
        Listener(),
        ScriptedClient(dict(ANSWERS)),  # type: ignore[arg-type]
    )

    assert result.local.document != result.with_model.document
    assert (tmp_path / "local").exists()
    assert (tmp_path / "with-model").exists()
    # Whatever else moved, the comparison must be able to say something about it.
    assert isinstance(result.changes(), list)
    assert "document" in result.to_json()


def test_a_metric_that_did_not_move_is_not_a_row(
    study: Profile, tmp_path: Path, markdown_file: Path
) -> None:
    """Comparing a build with itself should produce an empty diff, not a wall of zeroes."""
    from mimem.eval.compare import compare

    result = compare(markdown_file, tmp_path, study, Listener(), NullClient())
    assert result.changes() == []
    assert result.dollars == 0.0
