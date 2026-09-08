"""ElevenLabs, which needs its own adapter and a WAV header the API does not send.

Every other engine in :mod:`mimem.speak` either speaks the OpenAI ``/audio/speech`` shape or is
a local process. ElevenLabs is neither: it has its own endpoint, its own auth header, and its
own idea of what "audio" means on the way out. Hence a file rather than another branch.

**It will not send you a WAV.** The output formats are MP3, raw PCM, and mu-law. MP3 does not
concatenate; mu-law is not what anything here wants; and raw PCM is *headerless*, so handing it
to :func:`mimem.speak.audio.decode` produces "did not return a WAV file" on audio that is
perfectly good. So this asks for PCM and puts the header on itself. That is four lines and the
whole reason the assembly layer can stay strict about formats.

**The per-character billing makes the chunk cache matter more here than anywhere.** Re-running a
twenty-minute programme after fixing one sentence is one chunk rather than ninety, which on this
provider is the difference between a rounding error and a real cost. Nothing extra was needed to
get that -- the cache keys on text plus engine fingerprint, and the fingerprint includes the
voice -- but it is worth knowing before pointing this at a book.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass

from mimem.speak.engine import EngineError, Voice

#: Where the API lives. Overridable mainly so a test can point it somewhere harmless.
BASE_URL = "https://api.elevenlabs.io/v1"

#: Rachel: the voice every ElevenLabs example uses, so a first run works with no ``--voice``.
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"

#: Their current multilingual model. Named rather than defaulted server-side, because which
#: model answered is a thing the audit trail should be able to say.
DEFAULT_MODEL = "eleven_multilingual_v2"

#: Sample rates the API offers as raw PCM, and what this asks for. 22.05 kHz matches what SAPI
#: and Piper emit, so a programme half-rendered by one engine and half by another still
#: concatenates -- which :mod:`mimem.speak.audio` would otherwise refuse, correctly.
PCM_RATES = (16000, 22050, 24000, 44100)
DEFAULT_RATE = 22050

#: PCM from this API is 16-bit mono, always. Not a guess: it is in the format name.
SAMPLE_WIDTH = 2
CHANNELS = 1

TIMEOUT = 180.0


def wrap_pcm(pcm: bytes, rate: int = DEFAULT_RATE) -> bytes:
    """Put a WAV header on headerless PCM.

    The API's ``pcm_*`` formats are exactly that -- samples, no container. Everything
    downstream of an engine reads WAV, deliberately, because a format everything agrees on is
    what lets :func:`mimem.speak.audio.encode` refuse to join clips that would change pitch.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


@dataclass(slots=True)
class ElevenLabsEngine:
    """The best voices available here, and the only engine that bills per character."""

    api_key: str | None = None
    voice: str = DEFAULT_VOICE
    model: str = DEFAULT_MODEL
    rate: int = DEFAULT_RATE
    base_url: str = BASE_URL
    name: str = "elevenlabs"

    @property
    def fingerprint(self) -> str:
        return f"elevenlabs/{self.model}/{self.voice}/{self.rate}"

    def _key(self) -> str:
        import os

        key = self.api_key or os.environ.get("ELEVENLABS_API_KEY") or ""
        if not key:
            raise EngineError(
                "elevenlabs needs a key: set ELEVENLABS_API_KEY, or pass --api-key. "
                "`mimem doctor` will tell you what this machine can reach."
            )
        return key

    def voices(self) -> list[Voice]:
        """The voices on this account, which is what makes ``--voice`` usable.

        The ids are opaque strings, so a listing that gives only ids would be no help; the name
        and the accent are what a person chooses by.
        """
        request = urllib.request.Request(
            f"{self.base_url}/voices", headers={"xi-api-key": self._key()}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise _http_error(exc, self.base_url) from exc
        except urllib.error.URLError as exc:
            raise EngineError(f"could not reach {self.base_url}: {exc.reason}") from exc

        found: list[Voice] = []
        for entry in payload.get("voices", []):
            labels = entry.get("labels") or {}
            found.append(
                Voice(
                    id=str(entry.get("voice_id", "")),
                    name=str(entry.get("name", "")),
                    locale=str(labels.get("accent", "")),
                )
            )
        return found

    def speak(self, text: str) -> bytes:
        if self.rate not in PCM_RATES:
            raise EngineError(f"elevenlabs serves PCM at {PCM_RATES}, not {self.rate}")
        body = json.dumps({"text": text, "model_id": self.model}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/text-to-speech/{self.voice}?output_format=pcm_{self.rate}",
            data=body,
            headers={"xi-api-key": self._key(), "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                pcm = bytes(response.read())
        except urllib.error.HTTPError as exc:
            raise _http_error(exc, self.base_url) from exc
        except urllib.error.URLError as exc:
            raise EngineError(f"could not reach {self.base_url}: {exc.reason}") from exc
        if not pcm:
            raise EngineError("elevenlabs returned no audio")
        return wrap_pcm(pcm, self.rate)


def _http_error(exc: urllib.error.HTTPError, base_url: str) -> EngineError:
    """Say what the status means here, rather than repeating the number."""
    detail = exc.read()[:400].decode("utf-8", errors="replace").strip()
    if exc.code == 401:
        return EngineError(f"elevenlabs rejected the key (401). Check ELEVENLABS_API_KEY: {detail}")
    if exc.code == 422:
        return EngineError(
            f"elevenlabs refused the request (422) -- usually an unknown voice id or model. "
            f"`mimem voices --engine elevenlabs` lists the ids on your account: {detail}"
        )
    if exc.code == 429:
        return EngineError(
            f"elevenlabs is rate-limiting or the character quota is spent (429): {detail}"
        )
    return EngineError(f"{base_url} returned {exc.code}: {detail}")
