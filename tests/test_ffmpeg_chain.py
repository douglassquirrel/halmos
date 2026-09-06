import pytest

from lib import edit, media

from conftest import pixel, requires_drawtext, requires_ffmpeg, requires_libass, stream_info

pytestmark = [pytest.mark.tier2, requires_ffmpeg]


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
def test_build_output_has_one_video_and_one_audio_stream_with_expected_codecs(
    tmp_path, lavfi_clip
):
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
    # Regression for TODO.md bug #3: audio ran 3.2s past the end of the video
    # because -shortest doesn't apply to a filter-graph output. Here the
    # narration recording (5s) is deliberately much longer than the shots'
    # total duration (2s), the way a real take that ran long would be - if
    # the atrim in build()'s audio filter chain were ever removed or broken,
    # the output audio stream would run to ~5s while the video stays at ~2s.
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
