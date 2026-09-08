"""The adapter layer (rule TTS-05): one interface, several ways of making sound.

An engine takes a string and returns WAV bytes. That is the whole contract, and it is small on
purpose. Everything that shapes *how* the programme sounds -- where the pauses fall, how long
they are, what order things are said in -- has already been decided by the planner and is
enforced by :mod:`mimem.speak.assemble`, identically for every engine. What is left for an
adapter to get wrong is only the voice.

This is what ``TTS-05``'s "engine choice must not change the content" is worth in practice: the
same script through the offline engine and through a hosted one differs in timbre and in
nothing else. The test suite asserts it by synthesising the same script twice and comparing the
chunk texts and the timing map.

**Four adapters.** ``silent`` needs nothing and makes correctly-shaped silence, which is how the
pipeline is tested on a machine with no audio stack and how you check a programme's length
before paying to voice it. ``sapi`` is already installed on every Windows machine. ``piper``
is a local neural engine, offline and free. ``openai`` speaks the ``/audio/speech`` shape that
OpenAI, VoiceStudio and several self-hosted servers all implement, so one adapter reaches all
of them.

**No SDK for the HTTP one.** It is a single POST returning bytes; ``urllib`` does that, and
adding ``httpx`` to the base install to avoid twenty lines would be a poor trade for a project
whose whole install is meant to be one ``uvx`` away.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from mimem.speak.audio import AudioError, Clip, Format, decode, silence

#: How long the ``silent`` engine pretends a word takes. Only used to give the timing map
#: something plausible to be a map of; nothing about the real engines depends on it.
SILENT_WPM = 150.0

#: Sample format the ``silent`` engine emits. 22.05 kHz mono is what Piper and SAPI both
#: default to, so a programme rendered silently has the same shape as a real one.
SILENT_FORMAT = Format(channels=1, sample_width=2, frame_rate=22050)

#: Give a hosted engine time to synthesise a long beat, but not forever.
HTTP_TIMEOUT = 120.0

#: A local engine that has not produced audio in this long is stuck, not slow.
SUBPROCESS_TIMEOUT = 180.0


class EngineError(RuntimeError):
    """The engine could not be reached, or refused to speak."""


@dataclass(frozen=True, slots=True)
class Voice:
    """One voice an engine can offer."""

    id: str
    name: str = ""
    locale: str = ""

    def __str__(self) -> str:
        parts = [self.id]
        if self.name and self.name != self.id:
            parts.append(f"({self.name})")
        if self.locale:
            parts.append(self.locale)
        return " ".join(parts)


@runtime_checkable
class Engine(Protocol):
    """What :mod:`mimem.speak.assemble` requires of a way of making sound."""

    name: str

    @property
    def fingerprint(self) -> str:
        """Everything about this engine that changes the audio.

        The cache key, so that switching voice re-synthesises rather than replaying the old
        voice from disk under the new name.
        """

    def voices(self) -> list[Voice]:
        """The voices available, or an empty list if the engine cannot enumerate them."""

    def speak(self, text: str) -> bytes:
        """WAV bytes for one chunk."""


# -- silent ---------------------------------------------------------------------------------


@dataclass(slots=True)
class SilentEngine:
    """Correctly-shaped silence, at the rate the profile assumes people speak.

    Not a mock that lives in the test suite: it is the only engine available on the CI runners,
    it is how you see a programme's true length and structure before spending anything on a
    voice, and it is what proves that a failure is in the adapter rather than in the assembly.
    """

    name: str = "silent"
    wpm: float = SILENT_WPM

    @property
    def fingerprint(self) -> str:
        return f"silent/{self.wpm:g}"

    def voices(self) -> list[Voice]:
        return [Voice(id="silence", name="no voice at all")]

    def speak(self, text: str) -> bytes:
        seconds = len(text.split()) / self.wpm * 60.0
        return _wav_bytes(silence(seconds, SILENT_FORMAT))


# -- Windows SAPI ---------------------------------------------------------------------------

#: Drives ``System.Speech`` through PowerShell rather than through a COM binding, because the
#: binding would be a Windows-only dependency in a cross-platform package for something
#: PowerShell already does in four lines. ``$Input`` is not used: the text arrives base64-encoded
#: in the script itself, so no quoting rule of PowerShell's can corrupt an apostrophe or a dash.
_SAPI_SCRIPT = """
Add-Type -AssemblyName System.Speech
$ErrorActionPreference = 'Stop'
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}'))
$out = '{outfile}'
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
{select}
$s.Rate = {rate}
$s.SetOutputToWaveFile($out)
$s.Speak($text)
$s.Dispose()
"""

_SAPI_VOICES = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | ForEach-Object {
  $i = $_.VoiceInfo
  Write-Output ($i.Name + '|' + $i.Culture.Name)
}
$s.Dispose()
"""


@dataclass(slots=True)
class SapiEngine:
    """The speech synthesiser already present on every Windows machine.

    Not a good voice. It is a free one that needs no key, no download and no network, which
    makes it the fastest way to find out whether a programme *works* -- whether the pauses land
    where thinking happens and the questions sound like questions -- before choosing a voice to
    listen to for forty minutes.
    """

    voice: str | None = None
    rate: int = 0  # SAPI's own scale, -10..10, 0 being normal
    name: str = "sapi"

    @property
    def fingerprint(self) -> str:
        return f"sapi/{self.voice or 'default'}/rate{self.rate}"

    def voices(self) -> list[Voice]:
        out = _powershell(_SAPI_VOICES, what="listing SAPI voices")
        found = []
        for line in out.splitlines():
            name, _, locale = line.strip().partition("|")
            if name:
                found.append(Voice(id=name, name=name, locale=locale))
        return found

    def speak(self, text: str) -> bytes:
        import base64
        import tempfile
        from pathlib import Path

        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        select = f"$s.SelectVoice('{self.voice}')" if self.voice else ""
        with tempfile.TemporaryDirectory(prefix="mimem-sapi-") as tmp:
            outfile = Path(tmp) / "chunk.wav"
            _powershell(
                _SAPI_SCRIPT.format(
                    payload=payload,
                    outfile=str(outfile).replace("'", "''"),
                    select=select,
                    rate=self.rate,
                ),
                what="SAPI synthesis",
            )
            if not outfile.exists():
                raise EngineError("SAPI produced no file")
            return outfile.read_bytes()


def _powershell(script: str, *, what: str) -> str:
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if exe is None:
        raise EngineError(
            "the sapi engine needs PowerShell, which was not found on PATH. "
            "It is Windows-only; try --engine piper or --engine openai elsewhere."
        )
    try:
        result = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError(f"{what} timed out after {SUBPROCESS_TIMEOUT:g}s") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise EngineError(f"{what} failed: {detail or 'no error message'}")
    return result.stdout.decode("utf-8", errors="replace")


# -- Piper ----------------------------------------------------------------------------------


@dataclass(slots=True)
class PiperEngine:
    """A local neural engine: offline, free, and considerably better than SAPI.

    Piper wants a voice model on disk (a ``.onnx`` and its ``.json``), which is a download the
    listener makes once. The adapter does not fetch it: a tool that silently pulls hundreds of
    megabytes from a third party the first time you run it is not a tool anyone should trust
    with their reading.
    """

    model: str | None = None
    binary: str = "piper"
    name: str = "piper"

    @property
    def fingerprint(self) -> str:
        return f"piper/{self.model or 'default'}"

    def voices(self) -> list[Voice]:
        return [Voice(id=self.model)] if self.model else []

    def speak(self, text: str) -> bytes:
        exe = shutil.which(self.binary)
        if exe is None:
            raise EngineError(
                f"{self.binary!r} is not on PATH. Install Piper and download a voice, "
                "then pass --voice /path/to/voice.onnx"
            )
        command = [exe, "--output_file", "-"]
        if self.model:
            command[1:1] = ["--model", self.model]
        try:
            result = subprocess.run(
                command,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"piper timed out after {SUBPROCESS_TIMEOUT:g}s") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise EngineError(f"piper failed: {detail or 'no error message'}")
        return result.stdout


# -- OpenAI-compatible HTTP -----------------------------------------------------------------


@dataclass(slots=True)
class OpenAICompatibleEngine:
    """Anything that serves ``POST /audio/speech``.

    OpenAI defined the shape; VoiceStudio and several self-hosted servers implement it, so
    pointing ``--base-url`` at a local process and pointing it at a paid API are the same code
    path. WAV is requested explicitly rather than accepting the default, which is MP3 and would
    not concatenate.
    """

    model: str = "tts-1"
    voice: str = "alloy"
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    name: str = "openai"

    @property
    def fingerprint(self) -> str:
        return f"openai/{self.base_url}/{self.model}/{self.voice}"

    def voices(self) -> list[Voice]:
        # The endpoint has no voice-listing method; the names are part of the model's contract.
        return [Voice(id=v) for v in ("alloy", "echo", "fable", "onyx", "nova", "shimmer")]

    def speak(self, text: str) -> bytes:
        key = self.api_key or os.environ.get("OPENAI_API_KEY") or ""
        body = json.dumps(
            {
                "model": self.model,
                "voice": self.voice,
                "input": text,
                "response_format": "wav",
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/audio/speech", data=body, headers=headers
        )
        if request.type not in {"http", "https"}:
            raise EngineError(f"--base-url must be http or https, not {request.type!r}")
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:400].decode("utf-8", errors="replace").strip()
            raise EngineError(f"{self.base_url} returned {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EngineError(f"could not reach {self.base_url}: {exc.reason}") from exc


# -- construction ---------------------------------------------------------------------------


@dataclass(slots=True)
class EngineOptions:
    """Everything the CLI can pass through to an adapter."""

    voice: str | None = None
    model: str | None = None
    rate: int = 0
    base_url: str | None = None
    api_key: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


#: Every adapter, by the name ``--engine`` takes.
ENGINES = ("silent", "sapi", "piper", "openai", "elevenlabs")


def create(name: str, options: EngineOptions | None = None) -> Engine:
    """Build an adapter by name, or say which names exist."""
    opts = options or EngineOptions()
    if name == "silent":
        return SilentEngine()
    if name == "sapi":
        return SapiEngine(voice=opts.voice, rate=opts.rate)
    if name == "piper":
        # Piper's "voice" *is* its model file, so --voice and --model are the same argument
        # here. Accepting both spellings avoids a wrong-flag error that says nothing useful.
        return PiperEngine(model=opts.model or opts.voice)
    if name == "openai":
        engine = OpenAICompatibleEngine(api_key=opts.api_key)
        if opts.model:
            engine.model = opts.model
        if opts.voice:
            engine.voice = opts.voice
        if opts.base_url:
            engine.base_url = opts.base_url
        return engine
    if name == "elevenlabs":
        # Imported here rather than at module scope: it is the one adapter with its own API
        # shape, and nothing else in this module should come to depend on it.
        from mimem.speak.elevenlabs import ElevenLabsEngine

        eleven = ElevenLabsEngine(api_key=opts.api_key)
        if opts.voice:
            eleven.voice = opts.voice
        if opts.model:
            eleven.model = opts.model
        return eleven
    raise EngineError(f"unknown engine {name!r}; available: {', '.join(ENGINES)}")


def _wav_bytes(clip: Clip) -> bytes:
    """A single clip as a WAV file. Local import keeps :mod:`audio` free of engine concerns."""
    from mimem.speak.audio import encode

    return encode([clip])


__all__ = [
    "ENGINES",
    "AudioError",
    "Engine",
    "EngineError",
    "EngineOptions",
    "OpenAICompatibleEngine",
    "PiperEngine",
    "SapiEngine",
    "SilentEngine",
    "Voice",
    "create",
    "decode",
]
