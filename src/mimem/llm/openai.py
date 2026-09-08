"""One adapter for every server that speaks ``POST /chat/completions``.

That shape is implemented by OpenAI, Azure, Groq, Together, OpenRouter, DeepInfra and
Fireworks, and also by Ollama, llama.cpp's server, LM Studio, vLLM and Jan. So a hosted API and
a model running on the listener's own laptop are the same code path with a different
``base_url``, which is the lesson the speech adapters in :mod:`mimem.speak` taught first: one
widely implemented shape reaches more engines than several vendor-specific adapters.

``urllib``, not an SDK. This is one POST returning JSON, and the whole install is meant to be a
single ``uvx`` away; adding ``httpx`` or ``openai`` to the base dependencies to save thirty
lines would be a poor trade.

**The hard part is not the request, it is getting a typed answer back.** Every task in this
pipeline wants a validated ``GlossOut``, ``FigureOut``, ``VerifyOut`` and so on, and servers
disagree completely about how to ask for that: OpenAI has ``response_format: json_schema``,
older and smaller servers have ``json_object`` and nothing else, and several local ones have
neither. So this negotiates, once, and remembers -- see :class:`Mode` and the ladder in
:meth:`OpenAICompatibleClient.complete`.

Degrading is always allowed and half-parsing never is. A model that cannot hold the schema
produces ``LLMRefusedError``, the elaboration layer takes that task's documented degradation
path, and the manifest says so. That is a smaller programme, which is a thing a listener can
notice and act on. A half-filled object is a wrong programme, which is not.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from enum import StrEnum
from typing import Any

from mimem.llm.client import (
    BaseClient,
    LLMRefusedError,
    LLMUnavailableError,
    Request,
    Response,
)

#: Where an OpenAI-compatible server usually lives. ``/v1`` included, because every one of these
#: mounts the API under it and leaving it off is the most common setup mistake.
OPENAI_BASE_URL = "https://api.openai.com/v1"

#: Local runtimes, by the port they listen on by default. Used by ``mimem doctor`` to find a
#: server the user has already started, and as the value of ``--base-url local``.
LOCAL_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "lm-studio": "http://localhost:1234/v1",
    "llama.cpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
}

#: A hosted model is slow when the document is long; a local one on CPU is slower still.
TIMEOUT = 300.0

#: How many times to hand a model its own validation error and ask again. Two, because a model
#: that cannot produce the shape twice will not produce it on the third attempt, and each try
#: costs the full prompt.
MAX_SCHEMA_RETRIES = 2


class Mode(StrEnum):
    """How this server takes a schema, discovered on the first request and then reused.

    Re-probing every call would triple the cost of a run against a server that only supports
    the bottom rung, and the answer never changes within a run.
    """

    #: ``response_format: {"type": "json_schema", ...}``. Validated server-side; the good case.
    SCHEMA = "json_schema"
    #: ``response_format: {"type": "json_object"}`` plus the schema in the prompt. The model is
    #: guaranteed to emit *some* JSON, and nothing more than that.
    JSON_OBJECT = "json_object"
    #: Nothing but a prompt. Whatever comes back is scraped for the first JSON object in it.
    PROMPTED = "prompted"


#: The rungs, in the order they are tried.
LADDER = (Mode.SCHEMA, Mode.JSON_OBJECT, Mode.PROMPTED)


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic's JSON schema, in the dialect OpenAI's strict mode insists on.

    Strict mode requires ``additionalProperties: false`` on every object and requires *every*
    property to be listed in ``required`` -- including the optional ones, which is not what
    "required" means anywhere else and is the reason this function exists rather than passing
    ``model_json_schema()`` straight through. Optionality is expressed by allowing null instead.
    """
    out = dict(schema)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        properties = {k: strict_schema(v) for k, v in out.get("properties", {}).items()}
        if properties:
            out["properties"] = properties
            out["required"] = list(properties)
    for key in ("items", "additionalProperties"):
        if isinstance(out.get(key), dict):
            out[key] = strict_schema(out[key])
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(out.get(key), list):
            out[key] = [strict_schema(s) if isinstance(s, dict) else s for s in out[key]]
    if isinstance(out.get("$defs"), dict):
        out["$defs"] = {k: strict_schema(v) for k, v in out["$defs"].items()}
    return out


def extract_json(text: str) -> dict[str, Any]:
    """The first JSON object in a reply, however the model decided to wrap it.

    Small models fence their output, apologise before it, or explain it afterwards. None of that
    is worth a retry when the object itself is right there, so this finds the first balanced
    ``{...}`` and parses it. If there is no object at all, that *is* worth a retry, and the
    caller raises.
    """
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(text[start : index + 1])
                if not isinstance(parsed, dict):
                    raise ValueError("the reply's JSON is not an object")
                return parsed
    raise ValueError("the reply's JSON object is not closed")


class OpenAICompatibleClient(BaseClient):
    """A live client for any server speaking the chat-completions shape."""

    def __init__(
        self,
        *,
        base_url: str = OPENAI_BASE_URL,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        mode: Mode | None = None,
        timeout: float = TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        #: ``None`` until the first request settles it; pin it to skip the negotiation.
        self.mode: Mode | None = mode
        #: How often a model failed to hold its schema. The plan asks for this to be recorded
        #: per provider, so that "which local models actually work" is a measurement.
        self.schema_retries = 0

    # -- the request ------------------------------------------------------------------------

    def _messages(self, request: Request, mode: Mode) -> list[dict[str, Any]]:
        system = f"{request.system}\n\n{request.document}".strip()
        if mode is not Mode.SCHEMA:
            # The server will not enforce the shape, so the prompt has to describe it. Kept out
            # of the SCHEMA path deliberately: repeating a schema the server is already
            # enforcing wastes prompt on every call of a long run.
            schema = json.dumps(request.schema.model_json_schema(), indent=2)
            system += (
                "\n\nReply with one JSON object and nothing else -- no prose, no code fence. "
                f"It must match this JSON schema:\n{schema}"
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": request.instruction}]
        for image in request.images:
            encoded = base64.b64encode(image).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
            )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

    def _payload(self, request: Request, mode: Mode) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model if request.model.startswith(("gpt", "o")) else self.model,
            "messages": self._messages(request, mode),
            "max_tokens": request.max_tokens,
            # Deterministic where the server honours it: two runs of the same document should
            # differ because the document changed, not because sampling did.
            "temperature": 0.0,
        }
        if mode is Mode.SCHEMA:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema.__name__,
                    "schema": strict_schema(request.schema.model_json_schema()),
                    "strict": True,
                },
            }
        elif mode is Mode.JSON_OBJECT:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=headers
        )
        if http.type not in {"http", "https"}:
            raise LLMUnavailableError(f"base_url must be http or https, not {http.type!r}")
        try:
            with urllib.request.urlopen(http, timeout=self.timeout) as response:
                parsed = json.loads(response.read())
                if not isinstance(parsed, dict):  # pragma: no cover - servers return objects
                    raise LLMUnavailableError("the server did not return a JSON object")
                return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode("utf-8", errors="replace").strip()
            raise _http_error(exc.code, detail, self.base_url) from exc
        except urllib.error.URLError as exc:
            raise LLMUnavailableError(
                f"could not reach {self.base_url}: {exc.reason}. "
                "Is the server running? `mimem doctor` will say."
            ) from exc
        except TimeoutError as exc:
            raise LLMUnavailableError(
                f"{self.base_url} did not answer in {self.timeout:g}s"
            ) from exc

    # -- the ladder -------------------------------------------------------------------------

    def complete(self, request: Request) -> Response:
        """Ask, negotiating the schema mechanism the first time and reusing it after."""
        rungs = [self.mode] if self.mode is not None else list(LADDER)
        last: Exception | None = None

        for mode in rungs:
            assert mode is not None
            try:
                response = self._attempt(request, mode)
            except _UnsupportedFormatError as exc:
                # This server does not take a schema that way; drop to the next rung. Only this
                # exception falls through -- a refusal or a network failure is not a reason to
                # try a weaker mechanism, it is a reason to stop.
                last = exc
                continue
            self.mode = mode
            return response

        raise LLMUnavailableError(f"{self.base_url} accepted no structured-output mode: {last}")

    def _attempt(self, request: Request, mode: Mode) -> Response:
        payload = self._payload(request, mode)
        errors: list[str] = []

        for attempt in range(MAX_SCHEMA_RETRIES + 1):
            raw = self._post(payload)
            text = _content_of(raw)
            try:
                data = self._validate(request, extract_json(text))
            except (ValueError, LLMRefusedError) as exc:
                errors.append(str(exc))
                if attempt == MAX_SCHEMA_RETRIES:
                    break
                self.schema_retries += 1
                # Hand the model its own mistake. This is the step that makes a small local
                # model usable at all, and it is also why the retry count is recorded: a
                # provider that needs it constantly is one to write down as marginal.
                payload["messages"] = [
                    *payload["messages"],
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            f"That did not match the schema: {exc}\n"
                            "Reply again with one JSON object and nothing else."
                        ),
                    },
                ]
                continue

            usage = raw.get("usage") or {}
            return Response(
                data=data,
                model=str(raw.get("model", payload["model"])),
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                cached_tokens=int(
                    (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                ),
            )

        raise LLMRefusedError(
            f"{request.task}: {payload['model']} did not produce {request.schema.__name__} "
            f"in {MAX_SCHEMA_RETRIES + 1} attempts ({mode.value}): {errors[-1]}"
        )


class _UnsupportedFormatError(RuntimeError):
    """This server rejected the way we asked for a schema. Try a simpler way."""


def _http_error(code: int, detail: str, base_url: str) -> Exception:
    """Turn an HTTP status into the error that says what the user should do about it."""
    lowered = detail.lower()
    if code == 400 and any(
        marker in lowered
        for marker in ("response_format", "json_schema", "json_object", "not supported")
    ):
        return _UnsupportedFormatError(detail)
    if code in {401, 403}:
        return LLMUnavailableError(
            f"{base_url} rejected the credentials ({code}). Check the API key. Detail: {detail}"
        )
    if code == 404:
        return LLMUnavailableError(
            f"{base_url}/chat/completions was not found (404). The base URL usually ends in "
            f"/v1 -- is the model name right, and is it pulled? Detail: {detail}"
        )
    if code == 429:
        return LLMUnavailableError(f"{base_url} is rate-limiting or out of quota (429): {detail}")
    return LLMUnavailableError(f"{base_url} returned {code}: {detail}")


def _content_of(raw: dict[str, Any]) -> str:
    try:
        choices = raw["choices"]
        message = choices[0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMUnavailableError(f"unexpected reply shape: {json.dumps(raw)[:300]}") from exc
    content = message.get("content")
    if isinstance(content, list):  # some servers return the content-parts form
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not content:
        # A refusal, or a tool call we did not ask for. Either way there is no object to read.
        raise LLMRefusedError(f"the model returned no content: {json.dumps(message)[:200]}")
    return str(content)
