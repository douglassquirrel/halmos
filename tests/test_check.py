import pytest
from conftest import load_script, requires_google_genai

from lib import gem, media

pytestmark = pytest.mark.tier1


@pytest.fixture
def check_cli():
    return load_script("0_check.py")


@requires_google_genai
def test_check_passes_when_everything_is_present(check_cli, monkeypatch, capsys):
    monkeypatch.setattr(check_cli, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(media, "ffmpeg_diagnostic", lambda: (True, ""))
    monkeypatch.setattr(media, "has_ffmpeg_filter", lambda name: True)
    monkeypatch.setattr(gem, "need_package", lambda: None)
    monkeypatch.setattr(gem, "api_key", lambda: "fake-key")

    check_cli.main()  # does not raise - everything is OK

    out = capsys.readouterr().out
    assert "MISSING" not in out
    assert "BROKEN" not in out
    assert "Run  python3 1_plan.py" in out


@requires_google_genai
def test_check_reports_whatever_need_package_says_on_failure(check_cli, monkeypatch, capsys):
    # 0_check.py delegates entirely to gem.need_package() for this check
    # (see lib/gem.py's own comment on why there's no version gate here
    # any more - two hard version floors were both wrong in practice) -
    # this just confirms 0_check.py surfaces whatever it says verbatim
    # rather than writing its own summary of it.
    monkeypatch.setattr(check_cli, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(media, "ffmpeg_diagnostic", lambda: (True, ""))
    monkeypatch.setattr(media, "has_ffmpeg_filter", lambda name: True)
    monkeypatch.setattr(gem, "api_key", lambda: "fake-key")

    def missing():
        import sys

        sys.exit("The google-genai package is not installed.")

    monkeypatch.setattr(gem, "need_package", missing)

    with pytest.raises(SystemExit):
        check_cli.main()

    out = capsys.readouterr().out
    assert "MISSING  the google-genai package" in out
    assert "not installed" in out
    assert "1 problem(s) found" in out


@requires_google_genai
def test_check_reports_every_problem_at_once_not_just_the_first(check_cli, monkeypatch, capsys):
    # The whole point of a preflight check is seeing everything wrong in one
    # pass, not fixing one thing, rerunning, and finding the next.
    monkeypatch.setattr(check_cli, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(media, "ffmpeg_diagnostic", lambda: (True, ""))
    monkeypatch.setattr(media, "has_ffmpeg_filter", lambda name: False)

    def missing_key():
        import sys

        sys.exit("No API key found.\n\n  (instructions)")

    monkeypatch.setattr(gem, "api_key", missing_key)

    with pytest.raises(SystemExit):
        check_cli.main()

    out = capsys.readouterr().out
    assert "MISSING  the caption-rendering library (libass)" in out
    assert "MISSING  the label-drawing library (drawtext)" in out
    assert "MISSING  an API key" in out
    assert "3 problem(s) found" in out


@requires_google_genai
def test_check_skips_library_checks_when_ffmpeg_itself_is_missing(check_cli, monkeypatch, capsys):
    # Reporting "MISSING libass" when ffmpeg isn't even installed would name
    # the wrong cause - has_ffmpeg_filter() already returns False safely
    # either way, but the message shouldn't blame the wrong thing.
    monkeypatch.setattr(check_cli, "which", lambda name: None)
    monkeypatch.setattr(media, "ffmpeg_diagnostic", lambda: (False, "ffmpeg is not on your PATH"))
    monkeypatch.setattr(gem, "api_key", lambda: "fake-key")

    with pytest.raises(SystemExit):
        check_cli.main()

    out = capsys.readouterr().out
    assert "MISSING  ffmpeg and/or ffprobe" in out
    assert "libass" not in out
    assert "drawtext" not in out
    assert "1 problem(s) found" in out


@requires_google_genai
def test_check_reports_a_broken_ffmpeg_distinctly_from_a_missing_one(
    check_cli, monkeypatch, capsys
):
    # Found live, 2026-09-07: a binary `which` finds can still crash (a
    # Homebrew shared-library mismatch, e.g. ffmpeg-full installed but not
    # yet on PATH since it's keg-only) - that's a different, more specific
    # problem than "not installed," and should say so with the real error,
    # not just fall back to the generic MISSING message. Skips the
    # libass/drawtext checks too, same as the missing case - there's no
    # point asking a binary that doesn't run for its filter list.
    monkeypatch.setattr(check_cli, "which", lambda name: "/opt/homebrew/bin/" + name)
    monkeypatch.setattr(
        media,
        "ffmpeg_diagnostic",
        lambda: (False, "dyld: Library not loaded: /opt/homebrew/opt/x265/lib/libx265.216.dylib"),
    )
    monkeypatch.setattr(gem, "api_key", lambda: "fake-key")

    with pytest.raises(SystemExit):
        check_cli.main()

    out = capsys.readouterr().out
    assert "BROKEN   ffmpeg is on your PATH but does not run" in out
    assert "libx265.216.dylib" in out
    assert "keg-only" in out
    assert "MISSING  ffmpeg and/or ffprobe" not in out
    assert "libass" not in out
    assert "1 problem(s) found" in out
