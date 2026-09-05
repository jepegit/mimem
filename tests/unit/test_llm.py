"""The transport layer: caching, cost control, and the schemas that refuse bad output.

None of this calls a model. That is the point of the module under test -- everything except the
live adapter is exercised here, and the live adapter is the one piece this repository has never
run (see the note in ``mimem/llm/client.py``).

The cost tests deliberately assert on *shape* rather than on exact dollars. The prices change,
the token estimate is approximate, and a test that pinned the number to two decimal places would
be testing the price table rather than the arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mimem.llm import (
    Cached,
    FixtureClient,
    GlossOut,
    Ledger,
    NullClient,
    Plan,
    RecordingClient,
    Request,
    Response,
    ScriptedClient,
    estimate,
    estimate_tokens,
)
from mimem.llm.client import LLMRefusedError, LLMUnavailableError
from mimem.llm.cost import BudgetExceededError
from mimem.llm.schemas import AnalogyOut, AnchorOut, FigureOut

ANSWER = {"short_def": "a thin crust", "long_def": "It forms on the anode.", "spoken": None}


def _request(instruction: str = "explain it") -> Request:
    return Request(
        task="gloss",
        system="house style",
        document="the paper",
        instruction=instruction,
        schema=GlossOut,
    )


# -- the schemas are the second line of defence -------------------------------------------------


def test_an_analogy_without_a_limit_is_refused() -> None:
    """Rule ANA-01, checked in the prompt, the schema and the linter. This is the schema."""
    with pytest.raises(ValidationError):
        AnalogyOut(text="it is like a scab", limit="")


def test_an_over_long_anchor_is_refused() -> None:
    """Rule IMG-01: an anchor the listener cannot hold is not an anchor."""
    with pytest.raises(ValidationError):
        AnchorOut(text=" ".join(["word"] * 60))


def test_a_figure_description_must_carry_its_confidence() -> None:
    """Rule FIG-07: the highest-hallucination-risk output in the system says how sure it is."""
    with pytest.raises(ValidationError):
        FigureOut.model_validate(
            {
                "statement": "Capacity against cycle number.",
                "kind": "line chart",
                "axes": "cycles along the bottom",
                "trend": "falls steadily",
                "claim": "gradual loss, not a cliff",
            }
        )


def test_a_client_rejects_output_that_does_not_fit_its_schema() -> None:
    client = ScriptedClient({"gloss": [{"short_def": "only this"}]})
    with pytest.raises(LLMRefusedError):
        client.complete(_request())


# -- the transports -----------------------------------------------------------------------------


def test_the_default_transport_refuses() -> None:
    """A build should not start billing because a flag was forgotten."""
    with pytest.raises(LLMUnavailableError):
        NullClient().complete(_request())


def test_a_fixture_miss_raises_rather_than_falling_through(tmp_path: Path) -> None:
    """A fixture run that silently starts spending money is the one thing nobody wants."""
    with pytest.raises(LLMUnavailableError):
        FixtureClient(tmp_path).complete(_request())


def test_recording_then_replaying_round_trips(tmp_path: Path) -> None:
    recorder = RecordingClient(ScriptedClient({"gloss": [ANSWER]}), tmp_path)
    first = recorder.complete(_request())
    replayed = FixtureClient(tmp_path).complete(_request())
    assert replayed.data == first.data


# -- the cache ----------------------------------------------------------------------------------


def test_the_second_identical_request_is_free(tmp_path: Path) -> None:
    inner = ScriptedClient({"gloss": [ANSWER]})
    cached = Cached(inner=inner, directory=tmp_path)
    first = cached.complete(_request())
    second = cached.complete(_request())
    assert second.data == first.data
    assert second.source == "cache"
    assert inner.calls == ["gloss"]  # the model was asked exactly once
    assert cached.stats.hits == 1


def test_a_different_prompt_is_a_different_question(tmp_path: Path) -> None:
    inner = ScriptedClient({"gloss": [ANSWER, ANSWER]})
    cached = Cached(inner=inner, directory=tmp_path)
    cached.complete(_request("explain it"))
    cached.complete(_request("explain it differently"))
    assert cached.stats.misses == 2


def test_a_schema_change_invalidates_the_cache() -> None:
    """An old answer validated against a different shape is not a hit, it is a strange afternoon."""
    same_prompt = {
        "task": "gloss",
        "system": "s",
        "document": "d",
        "instruction": "i",
        "schema": GlossOut,
    }
    assert Request(**same_prompt).digest() == Request(**same_prompt).digest()
    assert (
        Request(**{**same_prompt, "schema": AnchorOut}).digest() != Request(**same_prompt).digest()
    )


def test_the_model_is_part_of_the_key() -> None:
    base = {"task": "gloss", "system": "s", "document": "d", "instruction": "i", "schema": GlossOut}
    assert Request(**base, model="a").digest() != Request(**base, model="b").digest()


# -- cost ---------------------------------------------------------------------------------------


def test_a_dry_run_says_what_it_would_do() -> None:
    plan = Plan()
    for i in range(3):
        plan.add(_request(f"instruction {i}"))
    report = plan.report()
    assert "3 call(s)" in report
    assert "gloss" in report
    assert plan.total() > 0


def test_caching_the_prefix_is_the_difference_between_cheap_and_expensive() -> None:
    """The document is the same for every task; paying for it thirty times is the failure mode."""
    request = _request()
    assert estimate(request, cached_prefix=True) < estimate(request, cached_prefix=False)


def test_batching_halves_it() -> None:
    request = _request()
    assert estimate(request, batch=True) == pytest.approx(estimate(request) * 0.5)


def test_a_longer_document_costs_more() -> None:
    short = Request(task="gloss", system="s", document="d" * 100, instruction="i", schema=GlossOut)
    long = Request(
        task="gloss", system="s", document="d" * 100_000, instruction="i", schema=GlossOut
    )
    assert estimate(long) > estimate(short)
    assert estimate_tokens("d" * 100_000) > estimate_tokens("d" * 100)


def test_an_unknown_model_is_priced_as_the_dearest_one() -> None:
    """Guessing low on an unknown model makes the budget cap fire late, which is the wrong way
    to be wrong."""
    known = Request(
        task="gloss",
        system="s",
        document="d",
        instruction="i",
        schema=GlossOut,
        model="claude-haiku-4-5-20251001",
    )
    unknown = Request(
        task="gloss",
        system="s",
        document="d",
        instruction="i",
        schema=GlossOut,
        model="something-new",
    )
    assert estimate(unknown) > estimate(known)


def test_the_cap_fires_before_the_call_not_after() -> None:
    ledger = Ledger(cap=0.01)
    ledger.check(0.005)  # fine
    with pytest.raises(BudgetExceededError):
        ledger.check(0.02)


def test_a_free_response_costs_nothing() -> None:
    """Fixture and cache hits are not billable, and the ledger has to know that."""
    ledger = Ledger()
    ledger.record(Response(data=GlossOut(**ANSWER), model="scripted", source="fixture"))
    assert ledger.spent == 0.0
    assert ledger.calls == 0


def test_a_live_response_is_priced_from_its_own_usage() -> None:
    """The estimate is replaced by a measurement as soon as there is one."""
    ledger = Ledger()
    ledger.record(
        Response(
            data=GlossOut(**ANSWER),
            model="claude-opus-5",
            input_tokens=10_000,
            output_tokens=500,
            cached_tokens=8_000,
            source="live",
        )
    )
    assert ledger.spent > 0
    assert ledger.calls == 1
    assert "cached tokens" in ledger.summary()
