import difflib

import pytest

from lib import media

pytestmark = pytest.mark.tier1


def _words(text, start=0.0, step=0.5, gap=0.1):
    """Fake transcribe() output: one dict per word, evenly spaced."""
    out, t = [], start
    for w in text.split():
        out.append({"w": w, "s": round(t, 3), "e": round(t + step - gap, 3)})
        t += step
    return out


# ------------------------------------------------- next_longest_available_clip
@pytest.mark.parametrize(
    "dur,resolution,expected",
    [
        (4, "720p", 4),  # exact match, smallest option
        (6, "720p", 6),  # exact match, middle option
        (5, "720p", 6),  # rounds up to the next available length
        (0, "720p", 4),  # smallest duration still buys the smallest clip
        (8.5, "720p", None),  # over the largest available length
        (8, "1080p", 8),  # only option, exact match
        (0, "1080p", 8),  # only option, rounds up from nothing
        (9, "1080p", None),  # over the only (and largest) option
        (8, "4k", 8),
    ],
)
def test_next_longest_available_clip_rounds_up_to_an_allowed_length(dur, resolution, expected):
    assert media.next_longest_available_clip(dur, resolution) == expected


# -------------------------------------------------------------- find_retakes -
def test_find_retakes_no_repeat():
    words = _words("the quick brown fox jumps over the lazy dog today and tomorrow")
    assert media.find_retakes(words) == []


def test_find_retakes_adjacent_five_word_repeat():
    words = _words("one two three four five one two three four five six seven")
    cuts = media.find_retakes(words)
    assert len(cuts) == 1
    assert cuts[0]["len"] == 5
    assert cuts[0]["text"] == "one two three four five"
    assert cuts[0]["start"] == words[0]["s"]
    assert cuts[0]["end"] == words[5]["s"]


def test_find_retakes_repeat_starting_at_index_zero():
    words = _words("alpha beta gamma delta epsilon alpha beta gamma delta epsilon zeta")
    cuts = media.find_retakes(words)
    assert len(cuts) == 1
    assert cuts[0]["text"] == "alpha beta gamma delta epsilon"


def test_find_retakes_repeat_right_at_the_end():
    words = _words("intro line here now six seven eight nine ten six seven eight nine ten")
    cuts = media.find_retakes(words)
    assert len(cuts) == 1
    assert cuts[0]["text"] == "six seven eight nine ten"


def test_find_retakes_two_independent_repeats():
    words = _words(
        "one two three four five one two three four five six seven "
        "eight nine ten eleven six seven eight nine ten twelve"
    )
    cuts = media.find_retakes(words)
    assert len(cuts) == 2
    assert [c["text"] for c in cuts] == [
        "one two three four five",
        "six seven eight nine ten",
    ]


def test_find_retakes_ignores_punctuation_and_case():
    words = [
        {"w": "One,", "s": 0.0, "e": 0.2},
        {"w": "Two", "s": 0.3, "e": 0.5},
        {"w": "three", "s": 0.6, "e": 0.8},
        {"w": "four", "s": 0.9, "e": 1.1},
        {"w": "five.", "s": 1.2, "e": 1.4},
        {"w": "one", "s": 1.5, "e": 1.7},
        {"w": "two,", "s": 1.8, "e": 2.0},
        {"w": "THREE", "s": 2.1, "e": 2.3},
        {"w": "four", "s": 2.4, "e": 2.6},
        {"w": "five", "s": 2.7, "e": 2.9},
        {"w": "six", "s": 3.0, "e": 3.2},
        {"w": "seven", "s": 3.3, "e": 3.5},
    ]
    cuts = media.find_retakes(words)
    assert len(cuts) == 1
    assert cuts[0]["len"] == 5


def test_find_retakes_below_the_min_words_floor_is_not_detected():
    # "go stop go now" is only 4 words - under the default min_words=5 floor.
    words = _words("go stop go now go stop go now again please")
    assert media.find_retakes(words) == []


# ------------------------------------------------------------------- align ---
def test_align_happy_path_sets_audio_start_and_dur():
    words = _words("hello there world this is a test of alignment today")
    shots = [
        {"beat": "1", "text": "hello there world"},
        {"beat": "2", "text": "this is a test"},
        {"beat": "3", "text": "of alignment today"},
    ]
    out = media.align(words, shots)
    assert out[0]["audio_start"] == 0.0
    assert out[0]["dur"] == pytest.approx(1.45)
    assert out[1]["audio_start"] == pytest.approx(1.45)
    assert out[2]["audio_start"] == pytest.approx(3.45)
    assert out[2]["dur"] == pytest.approx(1.7)


def test_align_raises_when_a_beat_is_entirely_missing():
    words = _words("hello there world this is a test of alignment today")
    shots = [
        {"beat": "1", "text": "hello there world"},
        {"beat": "2", "text": "nonexistent phrase here"},
    ]
    with pytest.raises(ValueError, match="Could not find beats"):
        media.align(words, shots)


def test_align_averages_the_edge_when_word_timestamps_touch():
    # hw[lasts[0]]["e"] == hw[firsts[1]]["s"] exactly - the "b > a" branch is
    # false, so the edge must fall back to b rather than dividing by/averaging
    # into something before the boundary.
    words = [
        {"w": "one", "s": 0.0, "e": 1.0},
        {"w": "two", "s": 1.0, "e": 2.0},
        {"w": "three", "s": 2.0, "e": 2.0},
        {"w": "four", "s": 2.0, "e": 3.0},
        {"w": "five", "s": 3.0, "e": 4.0},
    ]
    shots = [{"beat": "1", "text": "one two"}, {"beat": "2", "text": "three four five"}]
    out = media.align(words, shots)
    assert out[0]["dur"] == pytest.approx(2.0)
    assert out[1]["audio_start"] == pytest.approx(2.0)


def test_align_raises_when_beats_come_out_of_order(monkeypatch):
    # Difflib's get_matching_blocks() is documented to return blocks that are
    # monotonically increasing in both i and j (CPython docs: "if (i, j, n)
    # and (i', j', n') are adjacent triples... then i+n <= i' and j+n <= j'").
    # Since align()'s `owner` list is itself non-decreasing in script order,
    # that invariant means firsts[] can never actually come out of order via
    # real difflib output when every beat has at least one match - the
    # out-of-order branch is a defensive check against an invariant that, as
    # far as we can tell, difflib itself never violates. It's exercised here
    # by faking a non-monotonic block list, to confirm the branch still does
    # the right thing if that assumption ever stops holding.
    class FakeMatcher:
        def __init__(self, *a, **k):
            pass

        def get_matching_blocks(self):
            return [(0, 3, 1), (2, 0, 1)]

    monkeypatch.setattr(difflib, "SequenceMatcher", FakeMatcher)
    words = _words("xx yy zz ww", step=1.0, gap=0.0)
    shots = [{"beat": "A", "text": "aa bb"}, {"beat": "B", "text": "cc dd"}]
    with pytest.raises(ValueError, match="came out of order"):
        media.align(words, shots)


# -------------------------------------------------------------- split_long ---
def test_split_long_leaves_a_shot_under_the_ceiling_untouched():
    words = _words("one two three four five")
    shots = [{"beat": "1", "text": "one two three four five", "audio_start": 0.0, "dur": 5.0}]
    out, made = media.split_long(words, shots, maxdur=8.0)
    assert out == shots
    assert made == []


def test_split_long_splits_at_a_clean_gap():
    words = _words(
        "one two three four five six seven eight nine ten eleven twelve", step=1.0, gap=0.0
    )
    shots = [
        {
            "beat": "1",
            "text": "one two three four five six seven eight nine ten eleven twelve",
            "audio_start": 0.0,
            "dur": 12.0,
        }
    ]
    out, made = media.split_long(words, shots, maxdur=8.0)
    assert made == ["1-i", "1-ii"]
    assert [sh["beat"] for sh in out] == ["1-i", "1-ii"]
    assert all(sh["dur"] <= 8.0 for sh in out)
    assert all(sh["split_from"] == "1" for sh in out)
    assert out[0]["text"] + " " + out[1]["text"] == (
        "one two three four five six seven eight nine ten eleven twelve"
    )


def test_split_long_with_no_valid_split_point_leaves_the_beat_unsplit():
    # Pinned down as current behaviour (SPEC.md Sec.9, decided 2026-09-06),
    # not treated as a bug fix in this pass: with only one candidate gap and
    # it sitting under the 1.2s-from-either-edge guard, split_long silently
    # leaves the over-length beat as-is rather than splitting or flagging it.
    words = [{"w": "hi", "s": 0.0, "e": 0.5}, {"w": "therefolks", "s": 0.5, "e": 8.5}]
    shots = [{"beat": "1", "text": "hi therefolks", "audio_start": 0.0, "dur": 8.5}]
    out, made = media.split_long(words, shots, maxdur=8.0)
    assert made == []
    assert out == shots
    assert out[0]["dur"] > 8.0  # still over the ceiling - the known gap


def test_split_long_caption_chunking_treats_a_split_beat_like_any_other():
    # Regression for TODO.md bug #4: a caption style once keyed off a beat
    # literally named "1", breaking the moment beat 1 got split into "1-i"/
    # "1-ii". edit._chunks doesn't special-case any beat name, so this is
    # really about the pipeline as a whole not reintroducing that coupling -
    # asserted here by confirming a split beat's text still chunks normally.
    from lib import edit

    words = _words(
        "one two three four five six seven eight nine ten eleven twelve", step=1.0, gap=0.0
    )
    shots = [
        {
            "beat": "1",
            "text": "one two three four five six seven eight nine ten eleven twelve",
            "audio_start": 0.0,
            "dur": 12.0,
        }
    ]
    out, made = media.split_long(words, shots, maxdur=8.0)
    assert made == ["1-i", "1-ii"]
    for sh in out:
        assert edit._chunks(sh["text"]) == [sh["text"]]
