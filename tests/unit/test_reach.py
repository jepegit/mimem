"""`mimem doctor`: what is reachable, and whether it says the useful thing when nothing is.

The case that matters is the empty one. A machine with no keys and no local runtime is the
default state of every new install, and it is the state this project is developed in; if the
report is unhelpful there it is unhelpful where it is needed most.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from mimem.cli import app
from mimem.llm.reach import Check, State, port_open, survey

runner = CliRunner()

KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine with nothing configured and nothing listening."""
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("mimem.llm.reach.port_open", lambda url, timeout=0.0: False)


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in KEYS:
        monkeypatch.setenv(key, "test-key")
    monkeypatch.setattr("mimem.llm.reach.port_open", lambda url, timeout=0.0: True)


def _named(checks: list[Check], group: str, name: str) -> Check:
    return next(c for c in checks if c.group == group and c.name == name)


def test_the_assistant_is_always_available(bare: None) -> None:
    """It needs no key, which is the whole reason it is the recommended route."""
    assert _named(survey(), "text generation", "assistant").state is State.READY


def test_a_bare_machine_reports_no_keys(bare: None) -> None:
    checks = survey()
    assert _named(checks, "text generation", "anthropic").state is State.MISSING_KEY
    assert _named(checks, "text generation", "openai").state is State.MISSING_KEY
    assert _named(checks, "text generation", "local").state is State.NOT_INSTALLED


def test_every_unusable_provider_says_what_to_type(bare: None) -> None:
    """A red line with no fix is a line that tells the user they are stuck."""
    missing = [c for c in survey() if not c.ok and c.group != "tools"]
    assert missing, "the bare fixture should leave something unusable"
    for check in missing:
        assert check.fix, f"{check.name} has no suggested fix"


def test_keys_in_the_environment_are_noticed(configured: None) -> None:
    checks = survey()
    assert _named(checks, "text generation", "anthropic").state is State.CONFIGURED
    assert _named(checks, "text generation", "local").state is State.CONFIGURED


def test_a_configured_key_is_not_called_ready(configured: None) -> None:
    """ "The key is set" and "the key works" are different claims, and the report says which."""
    assert _named(survey(), "text generation", "anthropic").state is not State.READY


def test_silence_is_always_a_speech_option(bare: None) -> None:
    assert _named(survey(), "speech", "silent").state is State.READY


def test_port_open_is_false_for_a_closed_port() -> None:
    # Port 1 is reserved and never served by anything on a developer machine.
    assert port_open("http://127.0.0.1:1/v1", timeout=0.2) is False


# -- the command -----------------------------------------------------------------------------


def test_doctor_runs_and_names_every_group(bare: None) -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    for group in ("text generation", "speech", "tools"):
        assert group in result.stdout


def test_doctor_points_a_stuck_user_at_the_route_that_works(bare: None) -> None:
    """With no keys and no server, the assistant is the only way to reach a model."""
    result = runner.invoke(app, ["doctor"])
    assert "assistant is your only route" in result.stdout


def test_doctor_says_it_did_not_call_anything(bare: None) -> None:
    assert "--live" in runner.invoke(app, ["doctor"]).stdout


def test_doctor_makes_no_network_call_without_live(
    bare: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diagnostic that spends money by default would be a poor diagnostic."""
    import mimem.llm.reach as reach

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("doctor probed a provider without --live")

    monkeypatch.setattr(reach, "probe", explode)
    assert runner.invoke(app, ["doctor"]).exit_code == 0


def test_probe_reports_an_unreachable_provider_rather_than_raising(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live probe must never take the whole report down with it."""
    import mimem.llm.reach as reach
    from mimem.llm.client import LLMUnavailableError

    def fail(name: str, model: str | None) -> str:
        raise LLMUnavailableError("nothing there")

    monkeypatch.setattr(reach, "_ping", fail)
    checked = reach.probe(_named(survey(), "text generation", "openai"))
    assert checked.state is State.UNREACHABLE
    assert "nothing there" in checked.detail


def test_probe_survives_an_unexpected_error(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mimem.llm.reach as reach

    def boom(name: str, model: str | None) -> str:
        raise ZeroDivisionError("something nobody predicted")

    monkeypatch.setattr(reach, "_ping", boom)
    assert reach.probe(_named(survey(), "text generation", "openai")).state is State.FAILED


def test_probe_leaves_the_assistant_alone(bare: None) -> None:
    """There is nothing to call: the model is the conversation."""
    import mimem.llm.reach as reach

    check = _named(survey(), "text generation", "assistant")
    assert reach.probe(check) == check
