import pytest

from lib import gem

pytestmark = pytest.mark.tier1


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


# ----------------------------------------------------- spent_so_far / budget -
def test_spent_so_far_with_no_log_is_zero(isolated_home):
    assert gem.spent_so_far() == 0.0


def test_spent_so_far_sums_well_formed_entries(isolated_home):
    gem.SPEND.write_text(
        "2026-09-06 10:00:00\tstill\t1a\t$0.0336\tframes/1a.png\n"
        "2026-09-06 10:00:01\tthink\t100+50 tok\t$0.6000\t\n"
    )
    assert gem.spent_so_far() == pytest.approx(0.0336 + 0.6000)


def test_spent_so_far_skips_a_malformed_dollar_field(isolated_home):
    gem.SPEND.write_text(
        "2026-09-06 10:00:00\tstill\t1a\t$0.0336\tframes/1a.png\n"
        "2026-09-06 10:00:01\tclip/lite\t2a\t$not-a-number\tgen/beat_2a.mp4\n"
        "2026-09-06 10:00:02\tmusic\t1 track\t$0.0800\taudio/music_bed.mp3\n"
    )
    assert gem.spent_so_far() == pytest.approx(0.0336 + 0.0800)


def test_check_budget_within_the_cap_does_not_raise(isolated_home):
    gem.check_budget(5.0, s={"max_spend_usd": 20.0})


def test_check_budget_over_the_cap_exits_with_the_totals(isolated_home):
    gem.SPEND.write_text("2026-09-06 10:00:00\tstill\t1a\t$16.00\tframes/1a.png\n")
    with pytest.raises(SystemExit) as exc_info:
        gem.check_budget(5.0, s={"max_spend_usd": 20.0})
    message = str(exc_info.value)
    assert "$21.00" in message  # 16.00 already spent + 5.00 about to spend
    assert "$20.00 ceiling" in message
    assert "$16.00" in message  # "Already spent" figure
