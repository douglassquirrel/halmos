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


requires_ffmpeg = pytest.mark.skipif(
    not (_have("ffmpeg") and _have("ffprobe")), reason="ffmpeg/ffprobe not installed"
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
