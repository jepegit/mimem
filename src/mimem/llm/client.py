"""Talking to a model, or deliberately not.

Four transports behind one protocol, and the reason there are four is that most of this system
should be developable, testable and runnable without spending anything:

* :class:`NullClient` refuses. This is ``--local`` mode: the deterministic pipeline runs, every
  elaboration task degrades along its documented path, and the manifest says what was skipped.
  It is also the honest default, because a build should not start billing because a flag was
  forgotten.
* :class:`FixtureClient` replays recorded responses, keyed by the hash of the request. This is
  what the tests use and what makes the worked example reproducible.
* :class:`RecordingClient` wraps a live client and writes fixtures as it goes, so a recorded set
  is a by-product of one real run rather than something anyone has to hand-write.
* :class:`AnthropicClient` is the live one.

**On the live client: it has not been run.** There is no API key in the environment this was
built in, so the code below has never made a request. It is type-checked against the installed
SDK -- which is worth something, and caught one real bug -- but type-checking is not the same as
working. Everything around it is exercised; this adapter is not, and saying so is more useful
than a confident silence. Validate it with one small document before pointing it at a book.
"""

from __future__ import annotations

import base64
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel, ValidationError

#: Default model. The plan's position: a cheaper worker model is a *measured* decision, not an
#: assumption, so the default is the capable one and downgrading is a config change you can
#: compare on the eval set.
DEFAULT_MODEL = "claude-opus-5"

#: Effort per task, following the plan: low for mechanical rewriting, high for the tasks where
#: the output is a judgement and a bad one is expensive to notice.
EFFORT_LOW = "low"
EFFORT_HIGH = "high"


class LLMUnavailableError(RuntimeError):
    """A model was configured but could not be reached."""


class NoProviderError(LLMUnavailableError):
    """No model is configured at all.

    A subclass rather than a message, because "you have no key" and "the server did not answer"
    need different sentences and different actions from the user, and the manifest should be
    able to tell them apart without matching on prose. See :class:`mimem.elaborate.Absence`.
    """


class LLMRefusedError(RuntimeError):
    """The model answered, but not with something the schema accepts."""


@dataclass(frozen=True)
class Request:
    """One task instance, split the way prompt caching wants it.

    ``system`` and ``document`` are the stable prefix -- the style rules and the source text,
    identical across dozens of calls for one document -- and ``instruction`` is the volatile
    suffix. With a paper's worth of tasks that split is the difference between a cheap run and
    an expensive one.
    """

    task: str
    system: str
    document: str
    instruction: str
    schema: type[BaseModel]
    model: str = DEFAULT_MODEL
    effort: str = EFFORT_LOW
    max_tokens: int = 1024
    meta: dict[str, str] = field(default_factory=dict)
    #: PNG bytes to send alongside the instruction, for the tasks that describe a picture.
    #:
    #: Not part of the cached prefix: an image is volatile suffix, and the cost model prices it
    #: as one. And it *is* part of the digest -- see :meth:`digest`, where leaving it out is the
    #: most dangerous single omission available in this file.
    images: tuple[bytes, ...] = ()

    def digest(self) -> str:
        """Content address for the cache and the fixture store (PLAN section 4, stage 6).

        Keyed on everything that can change the answer: the task, the whole prompt, the model,
        the schema, **and the image**. A schema change invalidates the cache, which is what you
        want -- an old answer validated against a different shape is not a hit.

        The image matters more than the rest of it put together. Every figure in a document
        produces a request with the same task, the same system prompt, the same document and
        very nearly the same instruction; the picture is the only thing that differs. Hash the
        text alone and the cache serves figure three's description for figure seven -- fluent,
        plausible, about the wrong picture, and with nothing downstream able to notice.
        """
        h = hashlib.blake2s(digest_size=16)
        for part in (
            self.task,
            self.system,
            self.document,
            self.instruction,
            self.model,
            self.effort,
            json.dumps(self.schema.model_json_schema(), sort_keys=True),
        ):
            h.update(part.encode("utf-8", errors="replace"))
            h.update(b"\x1f")
        for image in self.images:
            h.update(hashlib.blake2s(image, digest_size=16).digest())
            h.update(b"\x1f")
        return h.hexdigest()[:16]


@dataclass
class Response:
    """What came back, and what it cost."""

    data: BaseModel
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    source: str = "live"  # live | cache | fixture

    @property
    def billable(self) -> bool:
        return self.source == "live"


class Client(Protocol):
    """Anything that can answer a :class:`Request`."""

    def complete(self, request: Request) -> Response: ...


class BaseClient(ABC):
    """Shared validation, so every transport rejects the same malformed output."""

    @abstractmethod
    def complete(self, request: Request) -> Response: ...

    @staticmethod
    def _validate(request: Request, payload: dict[str, Any]) -> BaseModel:
        try:
            return request.schema.model_validate(payload)
        except ValidationError as exc:
            raise LLMRefusedError(
                f"{request.task}: output does not match its schema: {exc}"
            ) from exc


class NullClient(BaseClient):
    """Refuses every request. ``--local`` mode, and the default.

    Every caller of this module has a documented degradation path (figure to caption-only,
    anchor omitted, gloss to the source's own definition), so refusing produces a smaller
    programme rather than a failed build.
    """

    def complete(self, request: Request) -> Response:
        raise NoProviderError(
            f"no model configured for task {request.task!r}; running deterministic-only"
        )


class FixtureClient(BaseClient):
    """Replays recorded responses from a directory, keyed by request digest.

    Two uses. In tests it makes the elaboration layer deterministic and free. In the repository
    it holds the worked example from ``docs/examples/sample-output.md``, so that "the pipeline
    can produce the target rendering end to end" is a test rather than a claim.

    A miss raises rather than falling through to a live call: a fixture run that silently starts
    spending money is the one behaviour nobody wants from a fixture.
    """

    def __init__(self, directory: Path, strict: bool = True) -> None:
        self.directory = Path(directory)
        self.strict = strict
        self.misses: list[str] = []

    def path_for(self, request: Request) -> Path:
        return self.directory / f"{request.task}-{request.digest()}.json"

    def complete(self, request: Request) -> Response:
        path = self.path_for(request)
        if not path.exists():
            self.misses.append(f"{request.task}:{request.digest()}")
            if self.strict:
                raise LLMUnavailableError(f"no fixture at {path}")
            raise LLMUnavailableError(f"no fixture for {request.task}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Response(
            data=self._validate(request, payload["output"]),
            model=payload.get("model", request.model),
            source="fixture",
        )


class ScriptedClient(BaseClient):
    """Answers by task name, in order. For tests, and for demonstrating the shape of an output.

    :class:`FixtureClient` keys on the request digest, which is right for replaying a real run
    and wrong for writing a test: the digest depends on every character of the prompt, so
    rewording an instruction would invalidate a fixture that is testing something else entirely.
    Keying on the task name says what the test means -- "when the gloss task returns this, the
    programme should contain that".
    """

    def __init__(self, answers: dict[str, list[dict[str, Any]]]) -> None:
        self.answers = {task: list(items) for task, items in answers.items()}
        self.calls: list[str] = []

    def complete(self, request: Request) -> Response:
        self.calls.append(request.task)
        queue = self.answers.get(request.task)
        if not queue:
            raise LLMUnavailableError(f"nothing scripted for task {request.task!r}")
        payload = queue.pop(0)
        return Response(data=self._validate(request, payload), model="scripted", source="fixture")


class RecordingClient(BaseClient):
    """Wraps a live client and writes each answer to the fixture store as it arrives."""

    def __init__(self, inner: Client, directory: Path) -> None:
        self.inner = inner
        self.directory = Path(directory)

    def complete(self, request: Request) -> Response:
        response = self.inner.complete(request)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{request.task}-{request.digest()}.json"
        path.write_text(
            json.dumps(
                {
                    "task": request.task,
                    "model": response.model,
                    "instruction": request.instruction,
                    "output": response.data.model_dump(mode="json"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return response


def _message_content(request: Request) -> Any:
    """The user turn: the instruction, and the picture when the task is about one.

    The image goes *before* the instruction. The instruction ends by asking for an honest
    confidence, and a model that has already been shown what it is judging answers that better
    than one asked to hold the question and then look.
    """
    if not request.images:
        return request.instruction
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image).decode("ascii"),
            },
        }
        for image in request.images
    ]
    blocks.append({"type": "text", "text": request.instruction})
    return blocks


class AnthropicClient(BaseClient):
    """The live one. **Never exercised** -- see the module docstring.

    Written against the documented API: a structured-output request whose stable prefix (the
    style rules and the source document) is marked for prompt caching and whose volatile suffix
    is the per-task instruction.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_retries: int = 2,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LLMUnavailableError(
                "the anthropic package is not installed; `uv pip install -e '.[llm]'`"
            ) from exc
        self._sdk = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=max_retries)
        self.model = model

    def complete(self, request: Request) -> Response:  # pragma: no cover - needs a live key
        message = self._client.messages.create(
            model=request.model or self.model,
            max_tokens=request.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": request.document,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": _message_content(request)}],
            tools=[
                {
                    "name": "answer",
                    "description": f"Return the result of the {request.task} task.",
                    "input_schema": request.schema.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "answer"},
        )
        from anthropic.types import ToolUseBlock

        payload = next(
            (
                block.input
                for block in message.content
                if isinstance(block, ToolUseBlock) and block.name == "answer"
            ),
            None,
        )
        if not isinstance(payload, dict):
            raise LLMRefusedError(f"{request.task}: the model returned no structured answer")
        usage = message.usage
        return Response(
            data=self._validate(request, cast(dict[str, Any], payload)),
            model=message.model,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            source="live",
        )
