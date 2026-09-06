import pytest

from lib import gem, media

from conftest import (
    FakeClient,
    FakeImageResponse,
    FakeTextResponse,
    FakeTranscribeResponse,
    fixture_text,
)

pytestmark = pytest.mark.tier3


# -------------------------------------------------------------- gem.ask() ----
def test_ask_parses_a_plain_json_response(monkeypatch, isolated_home):
    text = fixture_text("beats_plain.txt")
    monkeypatch.setattr(gem, "client", lambda: FakeClient(FakeTextResponse(text)))
    result = gem.ask("some prompt")
    assert result["beats"][0]["text"] == "Hello, world!"


def test_ask_parses_a_response_wrapped_in_a_json_fence(monkeypatch, isolated_home):
    text = fixture_text("beats_fenced.txt")
    monkeypatch.setattr(gem, "client", lambda: FakeClient(FakeTextResponse(text)))
    result = gem.ask("some prompt")
    assert result["beats"][1]["beat"] == "2"


def test_ask_parses_a_response_with_leading_prose_and_no_fence(monkeypatch, isolated_home):
    text = fixture_text("beats_prose_prefix.txt")
    monkeypatch.setattr(gem, "client", lambda: FakeClient(FakeTextResponse(text)))
    result = gem.ask("some prompt")
    assert len(result["beats"]) == 2


def test_ask_raises_after_exhausting_retries_on_malformed_json(monkeypatch, isolated_home):
    monkeypatch.setattr(gem, "client", lambda: FakeClient(FakeTextResponse("not json at all")))
    sleeps = []
    monkeypatch.setattr(gem.time, "sleep", lambda s: sleeps.append(s))
    with pytest.raises(RuntimeError, match="model call failed after 3 tries"):
        gem.ask("some prompt", retries=3)
    # One sleep per failed attempt, with the documented fixed backoff.
    assert sleeps == [2, 5, 8]


# -------------------------------------------------------- media.make_still() -
def test_make_still_saves_the_returned_image(monkeypatch, isolated_home, tmp_path):
    monkeypatch.setattr(gem, "client", lambda: FakeClient(FakeImageResponse(b"fake-png-bytes")))
    outdir = tmp_path / "frames"
    outdir.mkdir()
    dst = media.make_still("1", "a prompt", "a style", outdir=str(outdir))
    assert dst == f"{outdir}/1.png"
    assert (outdir / "1.png").read_bytes() == b"fake-png-bytes"


def test_make_still_returns_none_when_no_image_comes_back(monkeypatch, isolated_home, tmp_path):
    monkeypatch.setattr(gem, "client", lambda: FakeClient(FakeImageResponse(None)))
    outdir = tmp_path / "frames"
    outdir.mkdir()
    assert media.make_still("1", "a prompt", "a style", outdir=str(outdir)) is None
    assert not (outdir / "1.png").exists()


def test_make_still_skips_regenerating_an_existing_still(monkeypatch, isolated_home, tmp_path):
    outdir = tmp_path / "frames"
    outdir.mkdir()
    (outdir / "1.png").write_bytes(b"already there")

    def boom():
        raise AssertionError("should not have called the model")

    monkeypatch.setattr(gem, "client", boom)
    dst = media.make_still("1", "a prompt", "a style", outdir=str(outdir))
    assert dst == f"{outdir}/1.png"
    assert (outdir / "1.png").read_bytes() == b"already there"


# --------------------------------------------------------- media.transcribe -
def test_transcribe_parses_word_timings(monkeypatch, isolated_home, tmp_path):
    import json

    payload = json.loads(fixture_text("transcript_words.json"))

    def fake_client():
        return FakeClient(FakeTranscribeResponse(payload))

    monkeypatch.setattr(gem, "client", fake_client)
    out_path = tmp_path / "words.json"
    words = media.transcribe("narration.m4a", out=str(out_path))

    assert [w["w"] for w in words] == ["hello", "there", "world"]
    assert words[0]["s"] == pytest.approx(0.1)
    assert words[0]["e"] == pytest.approx(0.4)
    saved = json.loads(out_path.read_text())
    assert saved["text"] == "hello there world"
    assert len(saved["words"]) == 3


def test_transcribe_exits_when_no_words_come_back(monkeypatch, isolated_home, tmp_path):
    monkeypatch.setattr(
        gem, "client", lambda: FakeClient(FakeTranscribeResponse({"text": "", "words": []}))
    )
    with pytest.raises(SystemExit, match="no word timings"):
        media.transcribe("narration.m4a", out=str(tmp_path / "words.json"))
