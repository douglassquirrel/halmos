import pathlib
import subprocess

import pytest
from conftest import (
    FakeClient,
    FakeImageResponse,
    FakeTextResponse,
    FakeTranscribeResponse,
    fixture_text,
    requires_ffmpeg,
    requires_google_genai,
)

from lib import gem, media

pytestmark = [pytest.mark.tier3, requires_google_genai]


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
    monkeypatch.setattr(gem.random, "uniform", lambda a, b: 0)  # deterministic: no jitter
    with pytest.raises(RuntimeError, match="model call failed after 3 tries"):
        gem.ask("some prompt", retries=3)
    # One sleep per failed attempt EXCEPT the last (no point backing off
    # right before giving up), following the documented exponential backoff.
    assert sleeps == [gem._backoff_base(0), gem._backoff_base(1)]


def test_ask_does_not_retry_an_unrecoverable_error(monkeypatch, isolated_home):
    # bad_key/billing/quota/model_not_found can't be fixed by retrying - a
    # regression here would mean an invalid key fails identically eleven
    # times instead of once, exactly what TODO.md's "fail once" item warned
    # against.
    class FakeAPIError(Exception):
        def __init__(self, message, code, status):
            super().__init__(message)
            self.code, self.status = code, status

    bad_key_response = FakeAPIError("API key not valid", 400, "INVALID_ARGUMENT")
    calls = []
    monkeypatch.setattr(gem, "client", lambda: FakeClient([bad_key_response]))
    monkeypatch.setattr(gem.time, "sleep", lambda s: calls.append(s))
    with pytest.raises(RuntimeError, match="API key was rejected"):
        gem.ask("some prompt", retries=3)
    assert calls == []  # never slept - failed on the very first attempt


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


@requires_ffmpeg
def test_make_still_converts_jpeg_bytes_to_a_real_png(monkeypatch, isolated_home, tmp_path):
    # Real captured behaviour, 2026-09-06: a live call to the still-image
    # model returned inline_data with mime_type "image/jpeg" - genuine JPEG
    # bytes - even though make_still() names every file .png. Previously
    # written verbatim: every still halmos ever generated was a JPEG wearing
    # a .png extension. Uses a real ffmpeg-generated JPEG here, not a
    # fabricated byte string, so this only passes if the bytes are actually
    # re-encoded to a real PNG, not just copied through.
    jpeg_path = tmp_path / "src.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64",
            "-frames:v",
            "1",
            "-f",
            "image2",
            "-vcodec",
            "mjpeg",
            str(jpeg_path),
        ],
        check=True,
        capture_output=True,
    )
    jpeg_bytes = jpeg_path.read_bytes()
    assert jpeg_bytes[:2] == b"\xff\xd8"  # real JPEG magic bytes, sanity check

    monkeypatch.setattr(
        gem,
        "client",
        lambda: FakeClient(FakeImageResponse(jpeg_bytes, mime_type="image/jpeg")),
    )
    outdir = tmp_path / "frames"
    outdir.mkdir()
    dst = media.make_still("1", "a prompt", "a style", outdir=str(outdir))

    written = pathlib.Path(dst).read_bytes()
    assert written[:8] == b"\x89PNG\r\n\x1a\n", "file is not actually a PNG"


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
