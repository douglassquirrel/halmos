import pathlib

import pytest
from conftest import requires_google_genai

from lib import gem

pytestmark = pytest.mark.tier1


def test_project_dir_defaults_to_the_current_directory():
    # Not isolated on purpose - this pins down the real default.
    assert gem.PROJECT_DIR == pathlib.Path.cwd()


# --------------------------------------------------------------- settings ----
def test_settings_uses_built_in_defaults_with_nothing_on_disk(isolated_home, isolated_user_config):
    s = gem.settings()
    assert s["max_spend_usd"] == 20.0
    assert s["words_per_minute"] == 130


def test_settings_prefers_the_project_folder_over_the_user_default(
    isolated_home, isolated_user_config
):
    (isolated_home / "settings.json").write_text('{"max_spend_usd": 5.0}')
    config_dir = isolated_user_config / ".config" / "halmos"
    config_dir.mkdir(parents=True)
    (config_dir / "settings.json").write_text('{"max_spend_usd": 99.0}')
    assert gem.settings()["max_spend_usd"] == 5.0


def test_settings_falls_back_to_the_user_level_default(isolated_home, isolated_user_config):
    # No settings.json in the project folder at all.
    config_dir = isolated_user_config / ".config" / "halmos"
    config_dir.mkdir(parents=True)
    (config_dir / "settings.json").write_text('{"max_spend_usd": 99.0}')
    assert gem.settings()["max_spend_usd"] == 99.0


# ------------------------------------------------------------- style_block ---
def test_style_block_missing_file_exits(isolated_home):
    with pytest.raises(SystemExit, match="Missing"):
        gem.style_block()


def test_style_block_strips_comments_and_collapses_whitespace(isolated_home):
    (isolated_home / "style_block.txt").write_text(
        "# this is a comment, ignored\n"
        "Cut paper on a linen background,\n"
        "  lit flat from directly above.\n"
        "# another comment\n"
        "No photographic human hands or bodies.\n"
    )
    text = gem.style_block()
    assert "#" not in text
    assert "comment" not in text
    assert text == (
        "Cut paper on a linen background, lit flat from directly above. "
        "No photographic human hands or bodies."
    )


def test_style_block_rejects_the_placeholder_text(isolated_home):
    (isolated_home / "style_block.txt").write_text(
        "Describe your look here - materials, lighting, camera, colours."
    )
    with pytest.raises(SystemExit, match="placeholder"):
        gem.style_block()


def test_style_block_rejects_content_under_sixty_chars(isolated_home):
    (isolated_home / "style_block.txt").write_text("Too short.")
    with pytest.raises(SystemExit, match="empty"):
        gem.style_block()


def test_style_block_accepts_an_explicit_path_override(isolated_home, tmp_path):
    # A shared style file can live outside the project folder entirely -
    # TODO.md item 3's worked example passes --style pointing elsewhere.
    shared = tmp_path / "elsewhere" / "house-style.txt"
    shared.parent.mkdir()
    shared.write_text("A shared look used by several different video projects at once.")
    # isolated_home's PROJECT_DIR has no style_block.txt at all - proves the
    # explicit path is used instead of the project-relative default.
    assert gem.style_block(path=shared) == (
        "A shared look used by several different video projects at once."
    )


# ----------------------------------------------------- spent_so_far / budget -
def test_spent_so_far_with_no_log_is_zero(isolated_home):
    assert gem.spent_so_far() == 0.0


def test_spent_so_far_sums_well_formed_entries(isolated_home):
    gem.spend_path().write_text(
        "2026-09-06 10:00:00\tstill\t1a\t$0.0336\tframes/1a.png\n"
        "2026-09-06 10:00:01\tthink\t100+50 tok\t$0.6000\t\n"
    )
    assert gem.spent_so_far() == pytest.approx(0.0336 + 0.6000)


def test_spent_so_far_skips_a_malformed_dollar_field(isolated_home):
    gem.spend_path().write_text(
        "2026-09-06 10:00:00\tstill\t1a\t$0.0336\tframes/1a.png\n"
        "2026-09-06 10:00:01\tclip/lite\t2a\t$not-a-number\tgen/beat_2a.mp4\n"
        "2026-09-06 10:00:02\tmusic\t1 track\t$0.0800\taudio/music_bed.mp3\n"
    )
    assert gem.spent_so_far() == pytest.approx(0.0336 + 0.0800)


def test_check_budget_within_the_cap_does_not_raise(isolated_home):
    gem.check_budget(5.0, s={"max_spend_usd": 20.0})


def test_check_budget_over_the_cap_exits_with_the_totals(isolated_home):
    gem.spend_path().write_text("2026-09-06 10:00:00\tstill\t1a\t$16.00\tframes/1a.png\n")
    with pytest.raises(SystemExit) as exc_info:
        gem.check_budget(5.0, s={"max_spend_usd": 20.0})
    message = str(exc_info.value)
    assert "$21.00" in message  # 16.00 already spent + 5.00 about to spend
    assert "$20.00 ceiling" in message
    assert "$16.00" in message  # "Already spent" figure


# ------------------------------------------------------ need_package -------
# README tells a real user to just `pip install google-genai` with no
# version pin at all, unlike requirements-dev.txt's own `>=2.22.0` floor for
# this venv - so a stale install can lack a field this code relies on
# (found live, 2026-09-07: ImageConfig's `image_size`, added in google-genai
# 1.27.0) and fail with a raw SDK validation error deep in a real run
# instead of a clear message up front.
def test_parse_version_reads_a_plain_semver():
    assert gem._parse_version("2.22.0") == (2, 22, 0)


def test_parse_version_drops_non_digit_suffixes():
    assert gem._parse_version("1.27.0rc1") == (1, 27, 0)


def test_parse_version_orders_correctly_for_comparison():
    assert gem._parse_version("1.27.0") < gem._parse_version("2.22.0")
    assert gem._parse_version("2.9.0") < gem._parse_version("2.10.0")  # not string-order


@requires_google_genai
def test_need_package_passes_when_the_installed_version_is_new_enough():
    gem.need_package()  # this venv's real google-genai is >= MIN_GOOGLE_GENAI_VERSION


@requires_google_genai
def test_need_package_exits_with_an_actionable_message_when_too_old(monkeypatch):
    import google.genai

    monkeypatch.setattr(google.genai, "__version__", "1.0.0", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        gem.need_package()
    message = str(exc_info.value)
    assert "1.0.0" in message
    assert "pip install --upgrade google-genai" in message
