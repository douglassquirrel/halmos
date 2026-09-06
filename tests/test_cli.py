import json

import pytest
from conftest import (
    FakeClient,
    FakeImageResponse,
    FakeTextResponse,
    FakeTranscribeResponse,
    load_script,
    requires_drawtext,
    requires_ffmpeg,
    requires_google_genai,
)

from lib import gem

pytestmark = pytest.mark.tier1

# Most tests below are marked @requires_google_genai even though none of them
# touch the SDK directly: main()'s very first action is gem.need_package(),
# which exits immediately if google-genai isn't importable - deliberately,
# so a user missing it hears about that before wasting time on anything
# else. That means every test that calls .main() needs the package
# importable just to reach the argument/path-validation logic it's actually
# testing. Tests that only call parse_args() (never reaching need_package())
# are the exception and carry no such marker.


@pytest.fixture
def plan_cli():
    return load_script("1_plan.py")


@pytest.fixture
def make_cli():
    return load_script("2_make.py")


# ------------------------------------------------------------ 1_plan.py CLI --
def test_plan_parses_all_three_flags(plan_cli):
    args = plan_cli.parse_args(
        ["--script", "s.txt", "--style", "st.txt", "--out", "/tmp/somewhere"]
    )
    assert args.script == "s.txt"
    assert args.style == "st.txt"
    assert args.out == "/tmp/somewhere"


def test_plan_out_defaults_to_current_directory(plan_cli):
    args = plan_cli.parse_args([])
    assert args.out == "."
    assert args.script is None
    assert args.style is None


@requires_google_genai
def test_plan_creates_the_out_directory_if_missing(plan_cli, tmp_path):
    # need_package()/need_ffmpeg() both pass on this machine (see requirements-
    # dev.txt / the venv), so main() gets as far as project_dir creation and
    # the script.txt existence check before needing a real script - that's
    # exactly the boundary this test is probing. A shared style file avoids
    # tripping the (earlier-checked) missing-style-block exit instead.
    shared_style = tmp_path / "house-style.txt"
    shared_style.write_text("A shared house style, long enough to pass the length check here.")
    project = tmp_path / "brand-new-project"
    assert not project.exists()
    with pytest.raises(SystemExit, match="There is no script at"):
        plan_cli.main(["--style", str(shared_style), "--out", str(project)])
    assert project.exists()


@requires_google_genai
def test_plan_exits_when_the_named_script_is_missing(plan_cli, tmp_path):
    (tmp_path / "style_block.txt").write_text(
        "A style block long enough to pass the sixty-character minimum length check."
    )
    with pytest.raises(SystemExit, match="There is no script at"):
        plan_cli.main(["--script", str(tmp_path / "nope.txt"), "--out", str(tmp_path)])


@requires_google_genai
def test_plan_exits_on_the_placeholder_script_text(plan_cli, tmp_path):
    (tmp_path / "style_block.txt").write_text(
        "A style block long enough to pass the sixty-character minimum length check."
    )
    script = tmp_path / "script.txt"
    script.write_text("Replace this file with your own script before running this.")
    with pytest.raises(SystemExit, match="placeholder text"):
        plan_cli.main(["--out", str(tmp_path)])


@requires_google_genai
def test_plan_exits_when_the_script_is_too_short(plan_cli, tmp_path):
    (tmp_path / "style_block.txt").write_text(
        "A style block long enough to pass the sixty-character minimum length check."
    )
    (tmp_path / "script.txt").write_text("Only a few words here.")
    with pytest.raises(SystemExit, match="too short"):
        plan_cli.main(["--out", str(tmp_path)])


@requires_google_genai
def test_plan_exits_when_the_script_is_too_long(plan_cli, tmp_path):
    (tmp_path / "style_block.txt").write_text(
        "A style block long enough to pass the sixty-character minimum length check."
    )
    (tmp_path / "script.txt").write_text(" ".join(["word"] * 401))
    with pytest.raises(SystemExit, match="over three minutes"):
        plan_cli.main(["--out", str(tmp_path)])


@requires_google_genai
def test_plan_style_source_can_point_outside_the_project_folder(plan_cli, tmp_path):
    # The missing-script exit happens after style resolution, so this proves
    # --style is read from wherever it's pointed - including outside --out -
    # without needing a full run (which would need a real script and a key).
    shared_style = tmp_path / "shared" / "house-style.txt"
    shared_style.parent.mkdir()
    shared_style.write_text("A shared house style, long enough to pass the length check here.")
    project = tmp_path / "project"
    with pytest.raises(SystemExit, match="There is no script at"):
        plan_cli.main(["--style", str(shared_style), "--out", str(project)])


@requires_google_genai
def test_plan_exits_on_missing_style_even_with_a_valid_out_dir(plan_cli, tmp_path):
    # style_block() is resolved before the script check, so a missing style
    # file (and no --style override) surfaces its own exit first.
    with pytest.raises(SystemExit, match="Missing"):
        plan_cli.main(["--out", str(tmp_path)])


class _FakeAPIError(Exception):
    """See tests/test_gem_errors.py - stands in for google.genai.errors.APIError."""

    def __init__(self, message, code, status):
        super().__init__(message)
        self.code, self.status = code, status


def _plan_project(tmp_path, n_words=45):
    words = [f"word{i}" for i in range(n_words)]
    script_text = " ".join(words)
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "script.txt").write_text(script_text)
    (project_dir / "style_block.txt").write_text(
        "Flat vector illustration, warm colours, no photographic hands, no text."
    )
    return project_dir, script_text


@requires_ffmpeg
@requires_google_genai
def test_plan_stops_immediately_on_an_unrecoverable_still_error(plan_cli, tmp_path, monkeypatch):
    # TODO.md item 2's "fail once, not eleven times" extended to stills:
    # media.make_still() calls gem.client() directly (no gem.ask() retry
    # wrapper around it), so 1_plan.py's own loop - previously with no error
    # handling at all here, a bare exception would have crashed with a raw
    # traceback - is what has to classify the error and stop, matching what
    # 2_make.py's clip loop already does.
    project_dir, script_text = _plan_project(tmp_path)
    beats_response = FakeTextResponse(json.dumps({"beats": [{"beat": "1", "text": script_text}]}))
    prompts_response = FakeTextResponse(
        json.dumps({"prompts": [{"beat": "1", "prompt": "a blue square"}]})
    )
    bad_key = _FakeAPIError("API key not valid", 400, "INVALID_ARGUMENT")
    # One FakeClient instance shared across every gem.client() call in this
    # run - see _run_plan_then_prepare_make below for why a lambda
    # constructing a fresh one per call would silently hand every call the
    # same first queued response instead of advancing through the queue.
    client = FakeClient([beats_response, prompts_response, bad_key])
    monkeypatch.setattr(gem, "client", lambda: client)

    with pytest.raises(SystemExit, match="Stopped at beat 1"):
        plan_cli.main(["--out", str(project_dir)])


@requires_ffmpeg
@requires_google_genai
def test_plan_stops_immediately_on_an_unrecoverable_review_error(plan_cli, tmp_path, monkeypatch):
    # Same fail-fast requirement for the still-review loop: plan.review_still
    # goes through gem.ask(), so an unrecoverable class comes back as a
    # gem.FatalModelError rather than a raw APIError - previously caught by
    # a bare "except Exception: continue" that would have silently skipped
    # every remaining beat's review one by one with zero indication anything
    # was wrong.
    import subprocess

    project_dir, script_text = _plan_project(tmp_path)
    jpeg_path = tmp_path / "still.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64",
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
    beats_response = FakeTextResponse(json.dumps({"beats": [{"beat": "1", "text": script_text}]}))
    prompts_response = FakeTextResponse(
        json.dumps({"prompts": [{"beat": "1", "prompt": "a blue square"}]})
    )
    image_response = FakeImageResponse(jpeg_path.read_bytes(), mime_type="image/jpeg")
    quota_error = _FakeAPIError("Quota exceeded for quota metric", 429, "RESOURCE_EXHAUSTED")
    client = FakeClient([beats_response, prompts_response, image_response, quota_error])
    monkeypatch.setattr(gem, "client", lambda: client)

    with pytest.raises(SystemExit, match="Stopped reviewing at beat 1"):
        plan_cli.main(["--out", str(project_dir)])


# ----------------------------------------------------------- 2_make.py CLI ---
def _write_plan(project, style_source=None):
    plan_data = {
        "video": "myvideo",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "beats": [{"beat": "1", "text": "hello there", "prompt": "a prompt"}],
    }
    if style_source:
        plan_data["style_source"] = str(style_source)
    (project / "plan.json").write_text(json.dumps(plan_data))


@requires_google_genai
def test_make_exits_when_plan_json_is_missing(make_cli, tmp_path):
    with pytest.raises(SystemExit, match="No plan.json at"):
        make_cli.main(["--project", str(tmp_path)])


@requires_google_genai
def test_make_exits_when_style_is_missing(make_cli, tmp_path):
    _write_plan(tmp_path)  # no style_source, and no style_block.txt in project
    with pytest.raises(SystemExit, match="Missing"):
        make_cli.main(["--project", str(tmp_path)])


@requires_google_genai
def test_make_uses_the_style_source_recorded_by_1_plan(make_cli, tmp_path):
    shared_style = tmp_path / "elsewhere" / "house-style.txt"
    shared_style.parent.mkdir()
    shared_style.write_text("A shared house style, long enough to pass the length check here.")
    _write_plan(tmp_path, style_source=shared_style)
    # No audio/ recording - proves style resolution succeeded (didn't exit)
    # by reaching the *next* validation gate instead.
    with pytest.raises(SystemExit, match="No recording found"):
        make_cli.main(["--project", str(tmp_path)])


@requires_google_genai
def test_make_style_flag_overrides_the_recorded_style_source(make_cli, tmp_path):
    recorded_style = tmp_path / "recorded-style.txt"
    recorded_style.write_text("A style long enough to pass the sixty-character minimum here.")
    override_style = tmp_path / "override-style.txt"
    override_style.write_text("A different style, also long enough to pass the length check.")
    _write_plan(tmp_path, style_source=recorded_style)
    with pytest.raises(SystemExit, match="No recording found"):
        make_cli.main(["--project", str(tmp_path), "--style", str(override_style)])


@requires_google_genai
def test_make_exits_when_no_recording_is_found(make_cli, tmp_path):
    (tmp_path / "style_block.txt").write_text(
        "A style block long enough to pass the sixty-character minimum length check."
    )
    _write_plan(tmp_path)
    (tmp_path / "audio").mkdir()
    with pytest.raises(SystemExit, match="No recording found"):
        make_cli.main(["--project", str(tmp_path)])


# ------------------------------------------ end-to-end project-dir plumbing --
def _run_plan_then_prepare_make(plan_cli, tmp_path, monkeypatch):
    """Runs 1_plan.py for real (only gem.client() faked) into a project
    folder that is not the current directory, then sets gem.client up for
    2_make.py's transcription call too - stopping just short of calling
    2_make.py's main(), so callers can each drive the clip-generation loop
    differently. Returns project_dir. Shared by several tests below."""
    import subprocess

    # 45 short, distinct, tightly-timed "words" - long enough to clear
    # 1_plan.py's 40-word floor, short enough (given the fake tight timing
    # below) to stay under split_long's ceiling so it isn't split further.
    words = [f"word{i}" for i in range(45)]
    script_text = " ".join(words)
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "script.txt").write_text(script_text)
    (project_dir / "style_block.txt").write_text(
        "Flat vector illustration, warm colours, no photographic hands, no text."
    )

    jpeg_path = tmp_path / "still.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64",
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

    beats_response = FakeTextResponse(json.dumps({"beats": [{"beat": "1", "text": script_text}]}))
    prompts_response = FakeTextResponse(
        json.dumps({"prompts": [{"beat": "1", "prompt": "a blue square"}]})
    )
    image_response = FakeImageResponse(jpeg_bytes, mime_type="image/jpeg")
    review_response = FakeTextResponse(
        json.dumps({"ok": True, "problems": [], "revised_prompt": ""})
    )

    # One FakeClient instance shared across every gem.client() call in this
    # run - a fresh FakeClient per call (e.g. a plain lambda constructing one
    # each time) would hand every call the same first queued item forever,
    # since each would get its own untouched copy of the queue.
    plan_client = FakeClient([beats_response, prompts_response, image_response, review_response])
    monkeypatch.setattr(gem, "client", lambda: plan_client)
    plan_cli.main(["--out", str(project_dir)])

    assert (project_dir / "plan.json").exists()
    assert (project_dir / "contact_sheet.png").exists()
    assert (project_dir / "frames" / "1.png").exists()
    plan_data = json.loads((project_dir / "plan.json").read_text())
    assert plan_data["style_source"] == str(project_dir / "style_block.txt")

    (project_dir / "audio").mkdir()
    (project_dir / "audio" / "narration.m4a").write_bytes(b"not real audio - transcribe is faked")
    step = 0.15  # tight enough that 45 words stay under the 8s split ceiling
    fake_words = {
        "text": script_text,
        "words": [
            {"word": w, "start_offset": f"{i * step:.3f}s", "end_offset": f"{i * step + step:.3f}s"}
            for i, w in enumerate(words)
        ],
    }
    make_client = FakeClient(FakeTranscribeResponse(fake_words))
    monkeypatch.setattr(gem, "client", lambda: make_client)
    return project_dir


@requires_ffmpeg
@requires_drawtext
@requires_google_genai
def test_full_plan_then_make_uses_only_the_project_folder(
    plan_cli, make_cli, tmp_path, monkeypatch
):
    # The real risk in TODO.md item 3's refactor isn't any one function - it's
    # whether the many changed call sites still compose correctly end to end.
    # This runs both commands as far as recording alignment - stopping short
    # of clip generation, which would need faking Veo's async operation-
    # polling protocol, a separate and much larger undertaking (the two tests
    # below cover the clip-generation error-handling logic a different way,
    # by faking media.make_clip_veo directly instead). Everything up to here
    # already exercises every changed path in both scripts: --out/--project
    # resolution, style_source round-tripping through plan.json, frames/work/
    # audio directory placement, and find_narration/read_corrections/
    # transcribe/align/split_long all reading from the project folder.
    import pathlib

    assert tmp_path != pathlib.Path.cwd()  # sanity: this test is pointless if they're equal
    cwd_before = set(pathlib.Path.cwd().iterdir())

    project_dir = _run_plan_then_prepare_make(plan_cli, tmp_path, monkeypatch)

    # No clip_path exists yet, so main() proceeds past transcription and
    # alignment (this test's real target) into clip generation, where it
    # correctly fails - FakeModels supports neither generate_videos() nor
    # the omni interactions API - and exits with the documented message.
    # That failure is expected and is exactly where this test's scope ends.
    with pytest.raises(SystemExit, match="Could not generate clips"):
        make_cli.main(["--project", str(project_dir)])

    # Proof the project-relative plumbing worked correctly all the way to
    # that point: transcribe() wrote words.json under work/, not project
    # root or cwd; no retake was found (all 45 words are distinct) so no
    # cleaned-up audio file was ever created.
    assert (project_dir / "work" / "words.json").exists()
    assert not (project_dir / "audio" / "narration_clean.m4a").exists()

    # And, the point of the whole test: nothing leaked into the real cwd.
    assert set(pathlib.Path.cwd().iterdir()) == cwd_before


@requires_ffmpeg
@requires_drawtext
@requires_google_genai
def test_make_stops_immediately_on_an_unrecoverable_clip_error(
    plan_cli, make_cli, tmp_path, monkeypatch
):
    # TODO.md item 2's "fail once, not eleven times": an invalid key or an
    # unbilled account fails identically for every clip, so it should stop
    # at the first one rather than working through the rest.
    from lib import media

    project_dir = _run_plan_then_prepare_make(plan_cli, tmp_path, monkeypatch)

    class FakeAPIError(Exception):
        def __init__(self, message, code, status):
            super().__init__(message)
            self.code, self.status = code, status

    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise FakeAPIError("API key not valid", 400, "INVALID_ARGUMENT")

    monkeypatch.setattr(media, "make_clip_veo", boom)
    monkeypatch.setattr(media, "make_clip_omni", boom)

    with pytest.raises(SystemExit, match="API key was rejected"):
        make_cli.main(["--project", str(project_dir)])

    # Only one beat/model combination was ever attempted before stopping -
    # not one attempt per (shot x clip_model) combination.
    assert len(calls) == 1


@requires_ffmpeg
@requires_drawtext
@requires_google_genai
def test_make_stops_once_every_clip_model_is_quota_exhausted(
    plan_cli, make_cli, tmp_path, monkeypatch
):
    from lib import media

    project_dir = _run_plan_then_prepare_make(plan_cli, tmp_path, monkeypatch)
    # This project's settings.json doesn't exist, so clip_models defaults to
    # ["lite", "fast", "omni"] (gem.settings()'s built-in default).

    class FakeAPIError(Exception):
        def __init__(self, message, code, status):
            super().__init__(message)
            self.code, self.status = code, status

    def quota_exhausted(*a, **k):
        raise FakeAPIError("Quota exceeded for quota metric", 429, "RESOURCE_EXHAUSTED")

    monkeypatch.setattr(media, "make_clip_veo", quota_exhausted)
    monkeypatch.setattr(media, "make_clip_omni", quota_exhausted)

    with pytest.raises(SystemExit, match="every model in clip_models"):
        make_cli.main(["--project", str(project_dir)])


@requires_ffmpeg
@requires_drawtext
@requires_google_genai
def test_make_stops_immediately_on_an_unrecoverable_inpoint_error(
    plan_cli, make_cli, tmp_path, monkeypatch
):
    # TODO.md item 2's "say what it was doing" extended past clip generation:
    # choose_inpoint() calls gem.ask() once per shot, so a FatalModelError
    # here should stop the whole loop with beat/spend context, the same way
    # an unrecoverable clip error already does - not silently fall back to a
    # centred crop for every remaining shot in a row.
    from lib import edit

    project_dir = _run_plan_then_prepare_make(plan_cli, tmp_path, monkeypatch)

    # Clip generation and music aren't what this test is about - skip both by
    # pre-creating their outputs, the same "already done, don't redo it"
    # check main() itself uses everywhere else.
    gen_dir = project_dir / "gen"
    gen_dir.mkdir()
    (gen_dir / "beat_1.mp4").write_bytes(b"not a real clip - existence is all that's checked")
    (project_dir / "audio" / "music_bed.mp3").write_bytes(b"not real music")

    def boom(*a, **k):
        raise gem.FatalModelError("Today's allowance for this model is used up.")

    monkeypatch.setattr(edit, "choose_inpoint", boom)

    with pytest.raises(SystemExit, match="Stopped at beat 1"):
        make_cli.main(["--project", str(project_dir)])
