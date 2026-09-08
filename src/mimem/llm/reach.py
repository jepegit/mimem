"""What AI is reachable from this machine, and what to do about each thing that is not.

``mimem doctor`` exists because of what a survey of this project's own development machine
found: no API key of any kind, no local model runtime installed, nothing listening on any of the
usual ports. Everything degraded correctly and the programme still built, which is the design
working -- but it also meant that the *only* AI path a new user could actually turn on was the
assistant one, and nothing said so. Without this, they meet each absence separately, as its own
confusing error, and conclude the tool is broken.

So every check here answers two questions, and the second one matters more: **is it reachable,
and if not, what is the exact next thing to type?**

A check that only reads an environment variable would be worse than nothing, because "the key is
set" and "the key works" are different claims and this project has already been burned once by
treating one as the other -- see the CI reports in ``docs/PLAN-ai.md``. So :func:`probe` makes a
real request when asked to, and the report says plainly which kind of check it ran.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from mimem.llm.openai import LOCAL_BASE_URLS

#: How long to wait for a local port to answer. A server that is up answers instantly; one that
#: is not refuses instantly. Anything slower is a firewall, and waiting will not help.
PORT_TIMEOUT = 0.35


class State(StrEnum):
    """How ready one provider is, in the order a reader should worry about them."""

    READY = "ready"
    #: Installed and configured, but the live check was not run (no ``--live``).
    CONFIGURED = "configured"
    MISSING_KEY = "no key"
    NOT_INSTALLED = "missing"
    UNREACHABLE = "unreachable"
    FAILED = "failed"

    @property
    def ok(self) -> bool:
        return self in {State.READY, State.CONFIGURED}


@dataclass(frozen=True)
class Check:
    """One provider, and what a user would have to do to use it."""

    group: str
    name: str
    state: State
    detail: str = ""
    #: The exact next thing to type, when there is one.
    fix: str = ""

    @property
    def ok(self) -> bool:
        return self.state.ok


#: Colour codes a subprocess wrote for a terminal that is not this report.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _one_line(message: str, limit: int = 90) -> str:
    """A subprocess failure, made fit for a table row."""
    return _ANSI.sub("", message).replace("\n", " ").strip()[:limit]


def port_open(url: str, timeout: float = PORT_TIMEOUT) -> bool:
    """Is something listening where this base URL says it should be?

    Cheaper and far more informative than an HTTP request against a server that is not running:
    a closed port is an instant, unambiguous "you have not started it yet", where a request
    would give a connection error the user has to interpret.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _text_checks() -> Iterator[Check]:
    yield Check(
        group="text generation",
        name="assistant",
        state=State.READY,
        detail="no key needed; the model is the conversation",
        fix="install the extension: docs/listening/assistant.md",
    )

    if os.environ.get("ANTHROPIC_API_KEY"):
        yield Check("text generation", "anthropic", State.CONFIGURED, "ANTHROPIC_API_KEY is set")
    else:
        yield Check(
            "text generation",
            "anthropic",
            State.MISSING_KEY,
            "",
            "export ANTHROPIC_API_KEY=sk-ant-...",
        )

    if os.environ.get("OPENAI_API_KEY"):
        yield Check("text generation", "openai", State.CONFIGURED, "OPENAI_API_KEY is set")
    else:
        yield Check(
            "text generation", "openai", State.MISSING_KEY, "", "export OPENAI_API_KEY=sk-..."
        )

    running = [name for name, url in LOCAL_BASE_URLS.items() if port_open(url)]
    if running:
        found = ", ".join(f"{n} on {urlparse(LOCAL_BASE_URLS[n]).port}" for n in running)
        yield Check(
            "text generation",
            "local",
            State.CONFIGURED,
            found,
            f"mimem build paper.pdf --llm --provider local --base-url {LOCAL_BASE_URLS[running[0]]}",
        )
    else:
        ports = ", ".join(str(urlparse(u).port) for u in LOCAL_BASE_URLS.values())
        yield Check(
            "text generation",
            "local",
            State.NOT_INSTALLED,
            f"nothing listening on {ports}",
            "ollama serve   (or start LM Studio / llama-server / vLLM)",
        )


def _speech_checks() -> Iterator[Check]:
    from mimem.speak.engine import SapiEngine

    yield Check("speech", "silent", State.READY, "always available; makes shaped silence")

    # Windows first, and PowerShell second. Checking only for `pwsh` looked equivalent and is
    # not: GitHub's Ubuntu runners ship PowerShell Core, so that version of this check went
    # looking for `System.Speech` on Linux, failed in the way a broken install would, and
    # turned a green suite red. SAPI is a Windows component; PowerShell is only how it is
    # reached.
    if sys.platform != "win32":
        yield Check(
            "speech",
            "sapi",
            State.NOT_INSTALLED,
            "Windows only",
            "use --engine piper or --engine openai here",
        )
    elif shutil.which("pwsh") or shutil.which("powershell"):
        try:
            voices = SapiEngine().voices()
        except Exception as exc:
            yield Check(
                "speech",
                "sapi",
                State.FAILED,
                _one_line(str(exc)),
                "try `Add-Type -AssemblyName System.Speech` in PowerShell to see the real error",
            )
        else:
            yield Check("speech", "sapi", State.READY, f"{len(voices)} voices installed")
    else:
        yield Check(
            "speech",
            "sapi",
            State.NOT_INSTALLED,
            "PowerShell not found on PATH",
            "install PowerShell, or use --engine openai",
        )

    if shutil.which("piper"):
        yield Check("speech", "piper", State.CONFIGURED, "binary on PATH", "pass --voice a.onnx")
    else:
        yield Check(
            "speech",
            "piper",
            State.NOT_INSTALLED,
            "not on PATH",
            "install Piper and download a voice",
        )

    if os.environ.get("OPENAI_API_KEY"):
        yield Check("speech", "openai", State.CONFIGURED, "OPENAI_API_KEY is set")
    else:
        yield Check("speech", "openai", State.MISSING_KEY, "", "export OPENAI_API_KEY=sk-...")


def _tool_checks() -> Iterator[Check]:
    if shutil.which("ffmpeg"):
        yield Check("tools", "ffmpeg", State.READY, "available for converting audio.wav")
    else:
        yield Check("tools", "ffmpeg", State.NOT_INSTALLED, "WAV output only", "optional")

    if shutil.which("uv"):
        yield Check("tools", "uv", State.READY, "the extension needs it at first start")
    else:
        yield Check(
            "tools", "uv", State.NOT_INSTALLED, "the Claude Desktop extension needs uv on PATH"
        )


def survey() -> list[Check]:
    """Everything, without making a single network request or spending anything."""
    return [*_text_checks(), *_speech_checks(), *_tool_checks()]


def probe(check: Check, *, model: str | None = None) -> Check:
    """Actually use a provider, rather than believing its configuration.

    Only called with ``--live``, and only on providers a survey already called usable, because
    this is the part that can cost a fraction of a cent.
    """
    if check.group != "text generation" or not check.ok:
        return check
    if check.name == "assistant":
        return check  # nothing to call: it is the conversation

    from mimem.llm.client import LLMRefusedError, LLMUnavailableError

    try:
        detail = _ping(check.name, model)
    except (LLMUnavailableError, LLMRefusedError) as exc:
        return Check(
            check.group, check.name, State.UNREACHABLE, _one_line(str(exc), 120), check.fix
        )
    except Exception as exc:
        return Check(check.group, check.name, State.FAILED, _one_line(str(exc), 120), check.fix)
    return Check(check.group, check.name, State.READY, detail, check.fix)


def _ping(name: str, model: str | None) -> str:
    """One tiny structured request, which is the only proof that a provider works."""
    from pydantic import BaseModel, Field

    from mimem.llm.client import Request

    class Ping(BaseModel):
        ok: bool = Field(description="always true")

    request = Request(
        task="ping",
        system="You are checking a connection.",
        document="",
        instruction='Reply with {"ok": true}.',
        schema=Ping,
        max_tokens=64,
    )

    if name == "anthropic":
        from mimem.llm.client import DEFAULT_MODEL, AnthropicClient

        client = AnthropicClient(model=model or DEFAULT_MODEL)
        response = client.complete(request)
        return f"answered as {response.model}"

    from mimem.llm.openai import OpenAICompatibleClient

    if name == "openai":
        client_oai = OpenAICompatibleClient(model=model or "gpt-4o-mini")
    else:
        base = next((u for u in LOCAL_BASE_URLS.values() if port_open(u)), None)
        if base is None:
            raise RuntimeError("no local server is listening any more")
        client_oai = OpenAICompatibleClient(base_url=base, model=model or "llama3.2")
    response = client_oai.complete(request)
    mode = client_oai.mode.value if client_oai.mode else "unknown"
    retries = f", {client_oai.schema_retries} schema retries" if client_oai.schema_retries else ""
    return f"answered as {response.model} via {mode}{retries}"
