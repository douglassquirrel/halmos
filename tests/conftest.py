import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import gem  # noqa: E402


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point gem.HERE/gem.SPEND at a scratch dir instead of the real checkout,
    so style_block()/settings()/spent_so_far() never see this repo's own
    style_block.txt, settings.json or spend.log."""
    monkeypatch.setattr(gem, "HERE", tmp_path)
    monkeypatch.setattr(gem, "SPEND", tmp_path / "spend.log")
    return tmp_path


def _have(binary):
    return shutil.which(binary) is not None


def _ffmpeg_has_filter(name):
    if not _have("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True).stdout
    return any(line.split()[1] == name for line in out.splitlines() if len(line.split()) > 1)


requires_ffmpeg = pytest.mark.skipif(
    not (_have("ffmpeg") and _have("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

# edit.build()'s caption burn-in needs the "ass" filter (libass) and
# contact_sheet()'s labelling needs "drawtext" (libfreetype) - neither is in
# Homebrew's plain `ffmpeg` formula as of this writing, only `ffmpeg-full`.
# See DIARY.md: the README's own "brew install ffmpeg" instruction currently
# produces a build that can't run 2_make.py at all.
requires_libass = pytest.mark.skipif(
    not _ffmpeg_has_filter("ass"), reason="ffmpeg built without libass (need ffmpeg-full)"
)
requires_drawtext = pytest.mark.skipif(
    not _ffmpeg_has_filter("drawtext"), reason="ffmpeg built without drawtext (need ffmpeg-full)"
)


@pytest.fixture
def lavfi_clip(tmp_path):
    """Generate a tiny synthetic video+audio clip with ffmpeg itself: colour
    bars and a tone, never a real recording. Returns a factory so tests can
    make more than one with different durations/colours."""

    def make(name, duration=1.0, color="red", freq=440):
        dst = tmp_path / name
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x240:d={duration}:r=30",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={freq}:duration={duration}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(dst),
            ],
            check=True,
            capture_output=True,
        )
        return dst

    return make


@pytest.fixture
def lavfi_audio(tmp_path):
    """Generate a tiny synthetic audio-only file (a sine tone) - stands in
    for a narration recording without ever using a real one."""

    def make(name, duration=1.0, freq=440):
        dst = tmp_path / name
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={freq}:duration={duration}",
                "-c:a",
                "aac",
                str(dst),
            ],
            check=True,
            capture_output=True,
        )
        return dst

    return make


@pytest.fixture
def lavfi_still(tmp_path):
    """Generate a tiny solid-colour still PNG - stands in for a generated
    frame without ever calling a model."""

    def make(name, color="red", size=200):
        dst = tmp_path / name
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={size}x{size}",
                "-frames:v",
                "1",
                str(dst),
            ],
            check=True,
            capture_output=True,
        )
        return dst

    return make


def pixel(path, x, y):
    """The RGB triple at one pixel of an image, via ffmpeg - avoids adding an
    image-processing dependency just for a handful of test assertions."""
    p = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"crop=1:1:{x}:{y}",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return tuple(p.stdout[:3])


def stream_info(path):
    """[{"codec_type":..., "codec_name":..., "duration": float|None}, ...]
    for every stream in a media file, via ffprobe."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    streams = json.loads(out)["streams"]
    for s in streams:
        if "duration" in s:
            try:
                s["duration"] = float(s["duration"])
            except (TypeError, ValueError):
                s["duration"] = None
    return streams
