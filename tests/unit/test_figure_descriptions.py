"""Stage C: saying what a figure shows, and refusing to (``PLAN-figures.md`` §3, §4).

Most of these are about the refusals. A figure description is the one output in the system whose
claims a listener cannot check — they have no access to the thing being described — so the
interesting behaviour is everything that stops one being spoken.

The numbers in the fixtures are the real ones from Figure 3 of the paper this was built against,
including the two a vision model actually got wrong: it read a 60.27% label as "~69%" and called
a 0.09% sliver "substantial at ~23%".
"""

from __future__ import annotations

import pytest

from mimem.config import Profile
from mimem.elaborate import figures as fig
from mimem.ir import Block, BlockKind, Document, SourceMeta
from mimem.llm.cost import PNG_MAGIC
from mimem.llm.schemas import FigureOut
from mimem.plan.beats import BeatFactory, exposition_beats

CAPTION = "Figure 3. Gas production composition and volume percentage of four samples."
REFERENCE = "Gas signals serve as the earliest precursor for battery thermal runaway."


def _doc(*, described: bool = False, image: str | None = "figures/figure-3.png") -> Document:
    meta: dict[str, object] = {
        "label": "figure",
        "number": "3",
        "subject": "Gas production composition and volume percentage of four samples",
        "references": ["p1"],
    }
    if image:
        meta["image"] = image
    blocks = [
        Block(id="p1", kind=BlockKind.PARAGRAPH, text=REFERENCE, order=0),
        Block(id="c1", kind=BlockKind.CAPTION, text=CAPTION, order=1, attrs={"caption": meta}),
    ]
    doc = Document(id="d1", source=SourceMeta(format="pdf"), blocks=blocks)
    if described:
        fig.store(doc.block("c1"), _compliant())
    return doc


def _compliant(**overrides: object) -> FigureOut:
    base = {
        "statement": "Gas composition differs sharply between the four cell chemistries",
        "kind": "set of four pie charts, one per sample",
        "axes": "each slice is a share of the total gas volume",
        "trend": "In the third sample one gas takes well over half the volume on its own.",
        "exceptions": "The fourth sample's largest share belongs to a different gas.",
        "claim": "Composition is a fingerprint of the chemistry.",
        "confidence": 0.8,
    }
    return FigureOut(**{**base, **overrides})  # type: ignore[arg-type]


# -- what gets asked --------------------------------------------------------------------------


def test_a_figure_becomes_a_task_with_its_own_source() -> None:
    tasks = fig.figure_tasks(_doc())
    assert len(tasks) == 1
    assert tasks[0].number == "3"
    assert CAPTION in tasks[0].source
    assert REFERENCE in tasks[0].source, "the sentences that refer to it are part of the check"


def test_a_table_is_never_sent_to_a_vision_model() -> None:
    """A table's content is text. Sending one would be asking a model to read a picture of words."""
    doc = _doc()
    doc.block("c1").attrs["caption"]["label"] = "table"
    assert fig.figure_tasks(doc) == []


# -- what gets refused ------------------------------------------------------------------------


def test_a_compliant_description_is_accepted() -> None:
    ok, findings = fig.accept(_compliant(), _doc().blocks[1].text + REFERENCE)
    assert ok and findings == []


def test_a_value_read_off_the_plot_is_refused() -> None:
    """Even when it is right. 60.27 is the real label and appears in no sentence, so from the
    text's point of view it is indistinguishable from a fabrication."""
    out = _compliant(trend="One gas takes 60.27 percent of the third sample.")
    ok, findings = fig.accept(out, CAPTION + REFERENCE)
    assert not ok
    assert [f.value for f in findings] == ["60.27"]


def test_the_error_a_real_model_made_is_refused() -> None:
    """It read the 60.27% label as "~69%" and called a 0.09% sliver "substantial at ~23%"."""
    out = _compliant(
        trend="CO dominates at 69 percent, with ethylene substantial at 23 percent.",
    )
    ok, findings = fig.accept(out, CAPTION + REFERENCE)
    assert not ok
    assert {f.value for f in findings} == {"69", "23"}


def test_a_reversed_direction_is_refused() -> None:
    """Unlike an anchor, a figure description is a claim about the document and faces this."""
    source = CAPTION + " Hydrogen production increases with temperature."
    out = _compliant(trend="Hydrogen production decreases with temperature.")
    ok, findings = fig.accept(out, source)
    assert not ok
    assert any(f.kind == "direction" for f in findings)


def test_an_unconfident_description_is_refused_even_when_nothing_is_wrong() -> None:
    """Rule FIG-07. A model that cannot resolve a plot does not fall silent, it writes something
    plausible, so the prompt asks for honest confidence and this is what honesty buys."""
    ok, findings = fig.accept(_compliant(confidence=0.3), CAPTION + REFERENCE)
    assert not ok
    assert findings == [], "nothing is wrong with it; it is simply not sure enough"


# -- what gets said ---------------------------------------------------------------------------


@pytest.fixture
def study() -> Profile:
    return Profile(name="study")


def test_an_undescribed_figure_still_announces_itself(study: Profile) -> None:
    """Every local build gets this, and it is never worse than saying nothing."""
    beats = exposition_beats(_doc().block("c1"), BeatFactory(profile=study), {})
    assert beats[0].text.startswith("There's a figure here showing")


def test_a_described_figure_is_spoken_in_template_order(study: Profile) -> None:
    beats = exposition_beats(_doc(described=True).block("c1"), BeatFactory(profile=study), {})
    text = beats[0].text
    order = [
        text.index("differs sharply"),
        text.index("pie charts"),
        text.index("share of the total"),
        text.index("well over half"),
        text.index("largest share belongs"),
        text.index("fingerprint"),
    ]
    assert order == sorted(order), "FIG-01 is an order, and the order is the rule"


def test_the_description_is_attributed_and_not_hedged(study: Profile) -> None:
    """The data is the paper's, so marking it as *ours* the way an anchor is would be wrong —
    but the listener still has to know where to go and check."""
    beats = exposition_beats(_doc(described=True).block("c1"), BeatFactory(profile=study), {})
    assert beats[0].text.startswith("Here's what the figure shows.")
    assert beats[0].generated is False
    assert beats[0].spans, "it describes the paper's own picture and can point at it"


def test_the_manifest_records_who_wrote_it(study: Profile) -> None:
    """Rule FIG-07: the highest-hallucination-risk output says so in the audit trail."""
    beats = exposition_beats(_doc(described=True).block("c1"), BeatFactory(profile=study), {})
    assert beats[0].provenance is not None
    assert beats[0].provenance.generator == "figure"


def test_every_field_becomes_its_own_sentence(study: Profile) -> None:
    """Joined raw, the fragments produced "It's four pie charts. each slice is a share", which an
    engine reads with the intonation of a continuation."""
    beats = exposition_beats(_doc(described=True).block("c1"), BeatFactory(profile=study), {})
    assert "Each slice is a share" in beats[0].text
    assert ". each" not in beats[0].text


def test_a_described_figure_passes_its_own_lint_rule(study: Profile) -> None:
    """FIG-01 used to require the word "axis" and to spell its kinds in the singular, so a
    compliant description of four pie charts failed on both counts."""
    from mimem.ir import Script
    from mimem.lint.script_rules import FigureDescriptionFollowsTemplate

    beats = exposition_beats(_doc(described=True).block("c1"), BeatFactory(profile=study), {})
    script = Script(doc_id="d1", source=SourceMeta(format="pdf"), opening=beats)
    assert FigureDescriptionFollowsTemplate().check(script) == []


# -- the card rule ------------------------------------------------------------------------------


def test_no_card_can_take_its_answer_from_a_caption() -> None:
    """The legend misread that started all this is invisible to every check here: no number is
    wrong, no direction reversed, and the sentence is fluent. As one spoken sentence that is a
    cost worth the feature. As a card it is that error rehearsed at expanding intervals.

    Both doors into a card's answer are the support pool and ``best_sentence``, and neither will
    look at a caption.
    """
    from mimem.plan.support import best_sentence

    doc = _doc(described=True)
    assert best_sentence([doc.block("c1")], Profile(name="study")) is None


# -- the API path -------------------------------------------------------------------------------


def test_two_figures_produce_two_cache_keys() -> None:
    """The most dangerous line in the plan. Every figure request shares a task, a system prompt,
    a document and nearly an instruction; the picture is the only thing that differs. Hash the
    text alone and the cache serves figure three's description for figure seven.
    """
    from mimem.llm.tasks import figure

    one, two = PNG_MAGIC + b"figure-one", PNG_MAGIC + b"figure-seven"
    a = figure(CAPTION, [REFERENCE], "document", one)
    b = figure(CAPTION, [REFERENCE], "document", two)
    assert a.digest() != b.digest(), "same prompt, different picture, same cache key"
    assert a.digest() == figure(CAPTION, [REFERENCE], "document", one).digest()
    assert a.digest() != figure(CAPTION, [REFERENCE], "document").digest()


def test_an_image_is_priced_as_a_suffix_not_a_cached_prefix() -> None:
    from mimem.llm.cost import estimate
    from mimem.llm.tasks import figure

    without = figure(CAPTION, [REFERENCE], "document")
    with_image = figure(CAPTION, [REFERENCE], "document", b"\x89PNG" + b"\x00" * 400)
    assert estimate(with_image, cached_prefix=True) > estimate(without, cached_prefix=True)


# -- the conversation path ----------------------------------------------------------------------


def test_next_figure_hands_over_a_picture(tmp_path, monkeypatch) -> None:
    """The whole reason stage C is free: the assistant is already vision-capable, so the crop
    goes to it as an image and the description comes back through the same gate the API uses."""
    import json

    from mcp.types import ImageContent

    from mimem.assistant import server

    programme = tmp_path / "programmes" / "p1"
    (programme / "figures").mkdir(parents=True)
    (programme / "figures" / "figure-3.png").write_bytes(PNG_MAGIC + bytes(64))
    (programme / "doc.ir.json").write_text(_doc().to_json(), encoding="utf-8")
    monkeypatch.setenv("MIMEM_WORKSPACE", str(tmp_path))

    out = server.next_figure("p1")
    assert len(out) == 2
    meta, image = out
    assert meta["figure_id"] == "c1"
    assert meta["caption"] == CAPTION
    assert REFERENCE in meta["source_sentences"]
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/png"
    json.dumps(meta)  # the metadata half has to survive the protocol


def test_a_described_figure_is_not_offered_again(tmp_path, monkeypatch) -> None:
    from mimem.assistant import server

    programme = tmp_path / "programmes" / "p1"
    (programme / "figures").mkdir(parents=True)
    (programme / "figures" / "figure-3.png").write_bytes(PNG_MAGIC)
    (programme / "doc.ir.json").write_text(_doc(described=True).to_json(), encoding="utf-8")
    monkeypatch.setenv("MIMEM_WORKSPACE", str(tmp_path))

    out = server.next_figure("p1")
    assert len(out) == 1 and out[0]["remaining"] == 0


def test_a_figure_with_no_crop_is_never_offered(tmp_path, monkeypatch) -> None:
    """Describing a figure from its caption alone is what the confidence field exists to refuse."""
    from mimem.assistant import server

    programme = tmp_path / "programmes" / "p1"
    programme.mkdir(parents=True)
    (programme / "doc.ir.json").write_text(_doc(image=None).to_json(), encoding="utf-8")
    monkeypatch.setenv("MIMEM_WORKSPACE", str(tmp_path))

    assert server.next_figure("p1")[0]["remaining"] == 0
