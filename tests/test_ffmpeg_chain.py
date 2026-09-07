import pathlib

import pytest
from conftest import pixel, requires_drawtext, requires_ffmpeg, requires_libass, stream_info

from lib import edit, media

pytestmark = [pytest.mark.tier2, requires_ffmpeg]


# ------------------------------------------------------- has_ffmpeg_filter ---
# Backs 0_check.py's environment check and tests/conftest.py's
# requires_libass/requires_drawtext skip-guards - one implementation, not
# duplicated between the app and the test suite.
def test_has_ffmpeg_filter_finds_a_filter_present_in_every_ffmpeg_build():
    assert media.has_ffmpeg_filter("scale") is True


def test_has_ffmpeg_filter_is_false_for_a_made_up_name():
    assert media.has_ffmpeg_filter("not_a_real_filter_xyz") is False


# -------------------------------------------------------- ffmpeg_diagnostic --
# Found live, 2026-09-07: `which ffmpeg` finding a binary is not proof it
# actually runs - a Homebrew shared-library mismatch (e.g. after installing
# ffmpeg-full alongside an existing plain ffmpeg) can leave a binary that
# `which` finds but that crashes with a dyld "Library not loaded" error on
# every invocation, has_ffmpeg_filter() included (its ffmpeg -filters call
# would just come back empty, silently misreported as "missing libass").
def test_ffmpeg_diagnostic_ok_when_ffmpeg_runs():
    ok, detail = media.ffmpeg_diagnostic()
    assert ok is True
    assert detail == ""


def test_ffmpeg_diagnostic_reports_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr(media, "which", lambda name: None)
    ok, detail = media.ffmpeg_diagnostic()
    assert ok is False
    assert "not" in detail.lower()


def test_ffmpeg_diagnostic_reports_a_crash_with_the_real_stderr(monkeypatch):
    class FakeCompletedProcess:
        returncode = 1
        stdout = ""
        stderr = "dyld[123]: Library not loaded: /opt/homebrew/opt/x265/lib/libx265.216.dylib\n"

    monkeypatch.setattr(media, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: FakeCompletedProcess())
    ok, detail = media.ffmpeg_diagnostic()
    assert ok is False
    assert "libx265" in detail


def _basic_cfg(shots, sources, work, out, **extra):
    cfg = {
        "video": "testvid",
        "width": 320,
        "height": 240,
        "fps": 30,
        "shots": shots,
        "sources": sources,
        "target_lufs": -14,
        "caption_font_family": "",
        "caption_font_file": "",
    }
    cfg.update(extra)
    return cfg, work, out


@requires_libass
def test_build_output_duration_matches_shot_durations(tmp_path, lavfi_clip):
    c1 = lavfi_clip("s0.mp4", duration=1.0, color="red")
    c2 = lavfi_clip("s1.mp4", duration=1.5, color="blue")
    shots = [
        {"beat": "1", "text": "hello there", "dur": 1.0, "src": "1", "in": 0},
        {"beat": "2", "text": "world now", "dur": 1.5, "src": "2", "in": 0},
    ]
    sources = {"1": {"file": str(c1)}, "2": {"file": str(c2)}}
    cfg, work, out = _basic_cfg(shots, sources, str(tmp_path / "work"), str(tmp_path / "out"))

    final, total = edit.build(cfg, work=work, out=out)

    assert total == pytest.approx(2.5)
    assert float(media.probe(final)) == pytest.approx(2.5, abs=0.05)


@requires_libass
def test_build_output_has_one_video_and_one_audio_stream_with_expected_codecs(tmp_path, lavfi_clip):
    c1 = lavfi_clip("s0.mp4", duration=1.0, color="green")
    shots = [{"beat": "1", "text": "hi", "dur": 1.0, "src": "1", "in": 0}]
    sources = {"1": {"file": str(c1)}}
    cfg, work, out = _basic_cfg(shots, sources, str(tmp_path / "work"), str(tmp_path / "out"))

    final, _ = edit.build(cfg, work=work, out=out)
    streams = stream_info(final)

    video = [s for s in streams if s["codec_type"] == "video"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    assert len(video) == 1
    assert len(audio) == 1
    assert video[0]["codec_name"] == "h264"
    assert audio[0]["codec_name"] == "aac"


@requires_libass
def test_build_audio_does_not_outrun_the_video(tmp_path, lavfi_clip, lavfi_audio):
    # Regression for TODO.md bug #3: audio once ran 3.2s past the end of the
    # video because -shortest doesn't apply to a filter-graph output. The
    # narration recording here (5s) is deliberately much longer than the
    # shots' total duration (2s), the way a real take that ran long would be.
    #
    # build()'s audio chain now has two independent safeguards against this:
    # the explicit `atrim=0:{total}` in the filter graph, and the global
    # `-shortest` output flag. Verified by mutation-testing each alone (this
    # ffmpeg version's -shortest already truncates filter-graph audio
    # correctly on its own, so removing only atrim doesn't reproduce the
    # historical bug) and both together (which does: audio comes back at the
    # full ~5s while video stays at ~2s). This test asserts the *observable*
    # behaviour - the two streams end up close together - regardless of which
    # safeguard is doing the work, so it stays valid if either implementation
    # detail changes as long as the guarantee holds.
    c1 = lavfi_clip("s0.mp4", duration=1.0, color="red")
    c2 = lavfi_clip("s1.mp4", duration=1.0, color="blue")
    narration = lavfi_audio("narration.m4a", duration=5.0, freq=300)
    shots = [
        {"beat": "1", "text": "hello there", "dur": 1.0, "src": "1", "in": 0},
        {"beat": "2", "text": "world now", "dur": 1.0, "src": "2", "in": 0},
    ]
    sources = {"1": {"file": str(c1)}, "2": {"file": str(c2)}}
    cfg, work, out = _basic_cfg(
        shots,
        sources,
        str(tmp_path / "work"),
        str(tmp_path / "out"),
        narration={"file": str(narration), "start": 0},
    )

    final, total = edit.build(cfg, work=work, out=out)
    streams = stream_info(final)
    video_dur = next(s["duration"] for s in streams if s["codec_type"] == "video")
    audio_dur = next(s["duration"] for s in streams if s["codec_type"] == "audio")

    assert total == pytest.approx(2.0)
    assert video_dur == pytest.approx(2.0, abs=0.05)
    # The historical bug produced audio ~3s longer than the video; assert the
    # two streams stay close together, not merely "some duration or other".
    assert audio_dur == pytest.approx(video_dur, abs=0.15)


@requires_libass
def test_loudness_lands_near_the_target(tmp_path, lavfi_clip, lavfi_audio):
    c1 = lavfi_clip("s0.mp4", duration=2.0, color="red")
    narration = lavfi_audio("narration.m4a", duration=2.0, freq=300)
    shots = [{"beat": "1", "text": "hello there world", "dur": 2.0, "src": "1", "in": 0}]
    sources = {"1": {"file": str(c1)}}
    target = -16
    cfg, work, out = _basic_cfg(
        shots,
        sources,
        str(tmp_path / "work"),
        str(tmp_path / "out"),
        narration={"file": str(narration), "start": 0},
        target_lufs=target,
    )

    final, _ = edit.build(cfg, work=work, out=out)
    measured = edit.loudness(final)

    assert measured is not None
    assert measured == pytest.approx(target, abs=1.5)


@requires_drawtext
def test_contact_sheet_tiles_have_distinct_content(tmp_path, lavfi_still, monkeypatch):
    # Regression for TODO.md bug #1: ffmpeg's tile filter tiles frames of one
    # STREAM over time, not several input files - the original bug produced
    # a sheet that was N copies of the first still. A test that only checks
    # the output file exists and has the right size would not have caught
    # that; this samples real pixel content from each tile to prove they
    # differ, using a solid, distinct colour per still for an unambiguous
    # signal.
    monkeypatch.chdir(tmp_path)
    colors = ["red", "lime", "blue"]
    beats = ["1", "2", "3"]
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for beat, color in zip(beats, colors):
        lavfi_still(f"frames/{beat}.png", color=color, size=200)

    dst = media.contact_sheet(beats, outdir="frames", dst="contact_sheet.png", cols=3)
    assert dst is not None

    # Each still scales to 360 wide (aspect-preserved from a 200x200 square,
    # so also 360 tall) plus an 8px pad border -> 368x368 tiles in a single
    # row of 3. Sample well away from the top-left label box on each.
    tile_w = 368
    pixels = [pixel(dst, k * tile_w + 300, 300) for k in range(3)]
    assert len(set(pixels)) == 3, f"expected 3 distinct tile colours, got {pixels}"


def test_contact_sheet_returns_none_with_no_stills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "frames").mkdir()
    assert media.contact_sheet(["1", "2"], outdir="frames", dst="contact_sheet.png") is None


@requires_drawtext
def test_contact_sheet_writes_a_caption_file_per_beat_when_texts_given(
    tmp_path, lavfi_still, monkeypatch
):
    # The picture alone only shows the beat name - a human reviewing the
    # sheet has no way to tell what each picture is SUPPOSED to be about
    # without also opening narration_script.txt side by side. Printing the
    # actual sentence on the tile itself closes that gap. Verified via the
    # caption file written for ffmpeg's textfile= (arbitrary sentence text
    # needs real escaping ffmpeg's inline text= can't safely give it -
    # apostrophes and colons are both meaningful to ffmpeg's own filter
    # syntax), not by trying to pixel-check rendered text.
    monkeypatch.chdir(tmp_path)
    beats = ["1", "2"]
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for beat in beats:
        lavfi_still(f"frames/{beat}.png", color="red", size=200)
    texts = {"1": "A bee leaves the hive: it's time to swarm.", "2": "It dances for the others."}

    dst = media.contact_sheet(
        beats, outdir="frames", dst="contact_sheet.png", work="work", texts=texts
    )

    assert dst is not None
    caption_files = sorted(pathlib.Path("work/sheet").glob("*.txt"))
    assert len(caption_files) == 2
    # Wrapped onto its own lines (the sentence is over 30 chars), but every
    # word - punctuation included - survives, in order.
    assert (
        caption_files[0].read_text().split() == "A bee leaves the hive: it's time to swarm.".split()
    )
    assert caption_files[1].read_text().strip() == "It dances for the others."


@requires_drawtext
def test_contact_sheet_wraps_a_long_caption_across_lines(tmp_path, lavfi_still, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    lavfi_still("frames/1.png", color="red", size=200)
    long_text = "one two three four five six seven eight nine ten eleven twelve thirteen"

    dst = media.contact_sheet(
        ["1"], outdir="frames", dst="contact_sheet.png", work="work", texts={"1": long_text}
    )

    assert dst is not None
    caption = pathlib.Path("work/sheet/000.txt").read_text()
    assert "\n" in caption  # wrapped across more than one line, not one long run


@requires_drawtext
def test_contact_sheet_skips_a_beat_with_no_text_entry(tmp_path, lavfi_still, monkeypatch):
    # texts is a dict that may not cover every beat (e.g. a beat added
    # after the fact) - must not crash on a missing key.
    monkeypatch.chdir(tmp_path)
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    lavfi_still("frames/1.png", color="red", size=200)

    dst = media.contact_sheet(
        ["1"], outdir="frames", dst="contact_sheet.png", work="work", texts={}
    )

    assert dst is not None
    assert list(pathlib.Path("work/sheet").glob("*.txt")) == []
