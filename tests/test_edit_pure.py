import pytest

from lib import edit

pytestmark = pytest.mark.tier1


# ------------------------------------------------------- _parse_fps ----------
# Regression coverage for TODO.md bug #2: ffprobe's stream=r_frame_rate output
# has one line per stream, and the audio stream reports "0/0". The original
# code parsed line 0 only but had no guard for a malformed/zero rate landing
# there; every shot silently fell back to a centred crop. _parse_fps is the
# extracted fallback logic, tested directly rather than through the
# live-model-calling choose_inpoint().


def test_parses_a_real_frame_rate():
    assert edit._parse_fps("30000/1001") == pytest.approx(30000 / 1001)


def test_parses_a_simple_integer_ratio():
    assert edit._parse_fps("25/1") == 25.0


def test_falls_back_to_24_on_zero_over_zero():
    assert edit._parse_fps("0/0") == 24.0


def test_falls_back_to_24_on_empty_string():
    assert edit._parse_fps("") == 24.0


def test_falls_back_to_24_on_garbage():
    assert edit._parse_fps("abc") == 24.0


def test_falls_back_to_24_on_no_slash():
    assert edit._parse_fps("30") == 24.0


def test_uses_first_line_of_multiline_output():
    # ffprobe's real -show_entries stream=r_frame_rate output: one line per
    # stream, video first. This is the exact shape choose_inpoint feeds it.
    assert edit._parse_fps("30/1\n0/0") == 30.0


def test_falls_back_to_24_when_video_stream_itself_is_broken():
    assert edit._parse_fps("0/0\n0/0") == 24.0


# --------------------------------------------------------------- _ass_time ---
def test_ass_time_at_zero():
    assert edit._ass_time(0) == "0:00:00.00"


def test_ass_time_sub_minute():
    assert edit._ass_time(5.4) == "0:00:05.40"


def test_ass_time_sub_hour():
    assert edit._ass_time(65.5) == "0:01:05.50"


def test_ass_time_over_an_hour():
    assert edit._ass_time(3661.25) == "1:01:01.25"


def test_ass_time_rounds_seconds_into_the_next_minute():
    # 59.999 formatted naively as "%05.2f" rounds its seconds field to 60.00,
    # an invalid ASS timestamp - it must carry into the minutes field instead.
    result = edit._ass_time(59.999)
    assert result == "0:01:00.00"
    assert not result.split(":")[-1].startswith("60")


def test_ass_time_rounds_minutes_into_the_next_hour():
    assert edit._ass_time(3599.999) == "1:00:00.00"


# ----------------------------------------------------------------- _chunks ---
def test_chunks_short_text_is_one_chunk():
    assert edit._chunks("short") == ["short"]


def test_chunks_splits_on_the_default_boundary():
    text = "one two three four five six seven eight nine"
    assert edit._chunks(text) == ["one two three four five six", "seven eight nine"]


def test_chunks_merges_a_short_tail_into_the_previous_chunk():
    # A tail under 3 words is folded into the previous chunk rather than
    # becoming its own tiny caption.
    text = "one two three four five six seven"
    assert edit._chunks(text) == ["one two three four five six seven"]


def test_chunks_keeps_a_tail_of_three_or_more_as_its_own_chunk():
    text = "one two three four five six seven eight nine"
    chunks = edit._chunks(text)
    assert len(chunks) == 2
    assert chunks[1] == "seven eight nine"


def test_chunks_extends_past_a_function_word_at_the_boundary():
    # "and" lands exactly on the 6-word boundary; since it's a function word
    # the split is pushed to the next word instead of cutting right after it.
    text = "one two three four five and six"
    assert edit._chunks(text) == ["one two three four five and six"]
