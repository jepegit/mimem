"""Stage 9: the hand-off to a speech engine (rules TTS-01..05, milestone M7).

Everything before this produces a script that is *meant* to be spoken. This turns it into
something you can play, and it is the point at which the project stops being a text pipeline.

The division of labour is the design: :mod:`chunks` says what to say and how long to wait,
:mod:`engine` makes sound and knows nothing else, :mod:`assemble` puts the silences in and
records where everything landed, :mod:`cache` makes the second run cheap.
"""

from mimem.speak.assemble import AUDIO_FILE, TIMINGS_FILE, Synthesis, Timing, synthesize
from mimem.speak.audio import AudioError, Clip, Format
from mimem.speak.cache import CACHE_DIR, SpeechCache, key_for
from mimem.speak.chunks import SpeechChunk, speech_chunks
from mimem.speak.elevenlabs import ElevenLabsEngine
from mimem.speak.encode import ConversionError, OutputFormat, to_mp3
from mimem.speak.engine import (
    ENGINES,
    Engine,
    EngineError,
    EngineOptions,
    OpenAICompatibleEngine,
    PiperEngine,
    SapiEngine,
    SilentEngine,
    Voice,
    create,
)

__all__ = [
    "AUDIO_FILE",
    "CACHE_DIR",
    "ENGINES",
    "TIMINGS_FILE",
    "AudioError",
    "Clip",
    "ConversionError",
    "ElevenLabsEngine",
    "Engine",
    "EngineError",
    "EngineOptions",
    "Format",
    "OpenAICompatibleEngine",
    "OutputFormat",
    "PiperEngine",
    "SapiEngine",
    "SilentEngine",
    "SpeechCache",
    "SpeechChunk",
    "Synthesis",
    "Timing",
    "Voice",
    "create",
    "key_for",
    "speech_chunks",
    "synthesize",
    "to_mp3",
]
