"""The OpenAI-compatible adapter, and the ladder that makes small servers usable.

Everything here runs against a fake server, because the point of the tests is the negotiation
and the parsing, not the network. What each test encodes is a way a real server differs from
the reference one -- refusing `json_schema`, fencing its JSON, apologising before it, returning
content in parts -- because that variation is the entire reason this adapter is more than a
`urlopen` call.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from pydantic import BaseModel, Field

from mimem.llm.client import LLMRefusedError, LLMUnavailableError, Request
from mimem.llm.openai import (
    LADDER,
    Mode,
    OpenAICompatibleClient,
    extract_json,
    strict_schema,
)


class Out(BaseModel):
    text: str = Field(max_length=100)
    score: float = 0.5


def _request(**kw: Any) -> Request:
    return Request(
        task="gloss",
        system="You explain things.",
        document="A paper about resonators.",
        instruction="Define drift.",
        schema=Out,
        **kw,
    )


class FakeServer:
    """Stands in for `urlopen`, and can be told to behave like a limited server."""

    def __init__(
        self,
        *,
        replies: list[str] | None = None,
        supports: set[Mode] | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        self.replies = replies or ['{"text": "a slow drift", "score": 0.9}']
        self.supports = supports if supports is not None else set(Mode)
        self.usage = usage or {}
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: float = 0.0) -> Any:
        payload = json.loads(request.data)
        self.payloads.append(payload)

        fmt = payload.get("response_format", {}).get("type")
        mode = {
            "json_schema": Mode.SCHEMA,
            "json_object": Mode.JSON_OBJECT,
            None: Mode.PROMPTED,
        }[fmt]
        if mode not in self.supports:
            raise _http_error(400, f'{{"error": "response_format {fmt} is not supported"}}')

        index = min(len(self.payloads) - 1, len(self.replies) - 1)
        body = {
            "model": payload["model"],
            "choices": [{"message": {"content": self.replies[index]}}],
            "usage": self.usage,
        }
        return _FakeResponse(json.dumps(body).encode())


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


def _http_error(code: int, body: str) -> Exception:
    import urllib.error

    return urllib.error.HTTPError("u", code, "err", {}, _BodyFile(body.encode()))  # type: ignore[arg-type]


class _BodyFile(io.BytesIO):
    """`HTTPError` treats its `fp` as a real file and closes it during collection.

    A plain object with only `read` looks fine until the garbage collector runs, at which point
    `__del__` raises `AttributeError: no attribute 'close'` and pytest reports it as an
    unraisable exception against whichever *other* test happened to be running -- which is how
    this arrived, as a failure in a test that passed in isolation.
    """


@pytest.fixture
def patch_urlopen(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def apply(server: FakeServer) -> FakeServer:
        import mimem.llm.openai as module

        monkeypatch.setattr(module.urllib.request, "urlopen", server)
        return server

    return apply


# -- the ladder ------------------------------------------------------------------------------


def test_a_capable_server_gets_the_schema(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    server = patch_urlopen(FakeServer())
    client = OpenAICompatibleClient(base_url="http://x/v1")
    response = client.complete(_request())

    assert isinstance(response.data, Out)
    assert client.mode is Mode.SCHEMA
    assert server.payloads[0]["response_format"]["type"] == "json_schema"


def test_a_server_without_json_schema_drops_a_rung(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    """Ollama and llama.cpp have taken `json_object` far longer than they have `json_schema`."""
    server = patch_urlopen(FakeServer(supports={Mode.JSON_OBJECT, Mode.PROMPTED}))
    client = OpenAICompatibleClient(base_url="http://x/v1")
    client.complete(_request())

    assert client.mode is Mode.JSON_OBJECT
    assert [p.get("response_format", {}).get("type") for p in server.payloads] == [
        "json_schema",
        "json_object",
    ]


def test_a_server_with_no_structured_output_still_works(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    server = patch_urlopen(FakeServer(supports={Mode.PROMPTED}))
    client = OpenAICompatibleClient(base_url="http://x/v1")
    client.complete(_request())

    assert client.mode is Mode.PROMPTED
    assert len(server.payloads) == 3  # one attempt per rung


def test_the_negotiated_mode_is_reused(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    """Re-probing every call would triple the cost of a run against a limited server."""
    server = patch_urlopen(FakeServer(supports={Mode.PROMPTED}))
    client = OpenAICompatibleClient(base_url="http://x/v1")
    client.complete(_request())
    before = len(server.payloads)
    client.complete(_request())

    assert len(server.payloads) == before + 1


def test_the_schema_is_only_put_in_the_prompt_when_the_server_will_not_enforce_it(
    patch_urlopen,  # type: ignore[no-untyped-def]
) -> None:
    strict = patch_urlopen(FakeServer())
    OpenAICompatibleClient(base_url="http://x/v1").complete(_request())
    assert "JSON schema" not in strict.payloads[0]["messages"][0]["content"]

    loose = patch_urlopen(FakeServer(supports={Mode.PROMPTED}))
    OpenAICompatibleClient(base_url="http://x/v1").complete(_request())
    assert "JSON schema" in loose.payloads[-1]["messages"][0]["content"]


# -- getting an object out of the reply ------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        '{"text": "a slow drift"}',
        'Here you go:\n```json\n{"text": "a slow drift"}\n```',
        'Sure! {"text": "a slow drift"} Hope that helps.',
        '{"text": "a slow drift"}\n\nLet me know if you need more.',
    ],
    ids=["bare", "fenced", "surrounded", "trailing-chat"],
)
def test_a_wrapped_object_does_not_need_a_retry(reply: str, patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    """Small models explain themselves. The object is still right there."""
    server = patch_urlopen(FakeServer(replies=[reply], supports={Mode.PROMPTED}))
    client = OpenAICompatibleClient(base_url="http://x/v1")
    response = client.complete(_request())

    assert isinstance(response.data, Out)
    assert client.schema_retries == 0
    assert len(server.payloads) == 3  # the three rungs, and no retry within the last


def test_a_string_containing_a_brace_does_not_end_the_object() -> None:
    assert extract_json('{"text": "a } brace", "score": 1}')["text"] == "a } brace"


def test_an_escaped_quote_does_not_end_the_string() -> None:
    assert extract_json(r'{"text": "say \"drift\"", "score": 1}')["score"] == 1


@pytest.mark.parametrize(
    "reply", ["no object at all", '{"text": "unclosed', '["not", "an object"]']
)
def test_unparseable_replies_raise(reply: str) -> None:
    with pytest.raises(ValueError):
        extract_json(reply)


def test_a_wrong_shape_is_retried_with_the_error(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    """The step that makes a small model usable: hand it its own validation failure."""
    server = patch_urlopen(
        FakeServer(
            replies=['{"score": 0.5}', '{"text": "a slow drift", "score": 0.5}'],
            supports={Mode.SCHEMA},
        )
    )
    client = OpenAICompatibleClient(base_url="http://x/v1")
    response = client.complete(_request())

    assert isinstance(response.data, Out)
    assert client.schema_retries == 1
    assert "did not match the schema" in server.payloads[-1]["messages"][-1]["content"]


def test_a_model_that_never_holds_the_schema_refuses_rather_than_half_parsing(
    patch_urlopen,  # type: ignore[no-untyped-def]
) -> None:
    """A smaller programme is a thing a listener can notice. A wrong one is not."""
    patch_urlopen(FakeServer(replies=['{"score": 0.5}'], supports={Mode.SCHEMA}))
    client = OpenAICompatibleClient(base_url="http://x/v1")

    with pytest.raises(LLMRefusedError, match="did not produce Out"):
        client.complete(_request())


# -- errors a user has to act on -------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (401, "rejected the credentials"),
        (404, "usually ends in /v1"),
        (429, "rate-limiting or out of quota"),
        (500, "returned 500"),
    ],
)
def test_http_failures_say_what_to_do(
    code: int,
    expected: str,
    patch_urlopen,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mimem.llm.openai as module

    def fail(request: object, timeout: float = 0.0) -> None:
        raise _http_error(code, "server said no")

    monkeypatch.setattr(module.urllib.request, "urlopen", fail)
    with pytest.raises(LLMUnavailableError, match=expected):
        OpenAICompatibleClient(base_url="http://x/v1").complete(_request())


def test_a_non_http_base_url_is_refused() -> None:
    client = OpenAICompatibleClient(base_url="file:///etc")
    with pytest.raises(LLMUnavailableError, match="http or https"):
        client.complete(_request())


# -- the strict-schema dialect ---------------------------------------------------------------


def test_optional_fields_are_still_required_in_strict_mode() -> None:
    """OpenAI's strict mode means something different by "required" than JSON Schema does."""
    out = strict_schema(Out.model_json_schema())
    assert out["additionalProperties"] is False
    assert set(out["required"]) == {"text", "score"}


def test_nested_objects_are_converted_too() -> None:
    class Inner(BaseModel):
        a: str

    class Outer(BaseModel):
        inner: Inner

    out = strict_schema(Outer.model_json_schema())
    assert out["$defs"]["Inner"]["additionalProperties"] is False


# -- images ----------------------------------------------------------------------------------


def test_an_image_is_sent_as_a_data_url(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    server = patch_urlopen(FakeServer())
    client = OpenAICompatibleClient(base_url="http://x/v1")
    client.complete(_request(images=(b"\x89PNG\r\n\x1a\nfake",)))

    parts = server.payloads[0]["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_usage_is_reported_when_the_server_sends_it(patch_urlopen) -> None:  # type: ignore[no-untyped-def]
    patch_urlopen(
        FakeServer(
            usage={
                "prompt_tokens": 1200,
                "completion_tokens": 90,
                "prompt_tokens_details": {"cached_tokens": 1000},
            }
        )
    )
    response = OpenAICompatibleClient(base_url="http://x/v1").complete(_request())
    assert (response.input_tokens, response.output_tokens, response.cached_tokens) == (
        1200,
        90,
        1000,
    )


def test_the_ladder_is_ordered_best_first() -> None:
    assert LADDER == (Mode.SCHEMA, Mode.JSON_OBJECT, Mode.PROMPTED)
