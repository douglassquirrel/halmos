import pytest

from lib import gem, plan

pytestmark = pytest.mark.tier1


# ------------------------------------------------------- split_into_beats ----
def test_split_into_beats_accepts_a_word_preserving_split(monkeypatch):
    script = "Hello, world! This is a test script."
    monkeypatch.setattr(
        gem,
        "ask",
        lambda *a, **k: {
            "beats": [
                {"beat": "1", "text": "Hello, world!"},
                {"beat": "2a", "text": "This is a test"},
                {"beat": "2b", "text": "script."},
            ]
        },
    )
    beats = plan.split_into_beats(script, wpm=130)
    assert [b["beat"] for b in beats] == ["1", "2a", "2b"]


def test_split_into_beats_rejects_a_split_that_drops_a_word(monkeypatch):
    script = "Hello, world! This is a test script."
    monkeypatch.setattr(
        gem,
        "ask",
        lambda *a, **k: {
            "beats": [
                {"beat": "1", "text": "Hello, world!"},
                {"beat": "2", "text": "This is a script."},  # dropped "test"
            ]
        },
    )
    with pytest.raises(ValueError, match="changed the wording"):
        plan.split_into_beats(script, wpm=130)


def test_split_into_beats_rejects_a_split_that_adds_a_word(monkeypatch):
    script = "Hello, world!"
    monkeypatch.setattr(
        gem,
        "ask",
        lambda *a, **k: {"beats": [{"beat": "1", "text": "Hello, big world!"}]},
    )
    with pytest.raises(ValueError, match="changed the wording"):
        plan.split_into_beats(script, wpm=130)


def test_split_into_beats_tolerates_punctuation_and_case_differences(monkeypatch):
    # words() lowercases and strips punctuation before comparing, so a beat
    # split doesn't have to preserve capitalisation or exact punctuation.
    script = "Hello, World! This is fine."
    monkeypatch.setattr(
        gem,
        "ask",
        lambda *a, **k: {
            "beats": [
                {"beat": "1", "text": "hello world"},
                {"beat": "2", "text": "this is fine"},
            ]
        },
    )
    beats = plan.split_into_beats(script, wpm=130)
    assert len(beats) == 2


def test_split_into_beats_warns_about_beats_over_the_ceiling(monkeypatch):
    # At 60 wpm, maxwords = int(8*60/60) = 8, so a beat needs > 12 words
    # (maxwords + 4) to trigger the warning.
    long_text = " ".join(["word"] * 13)
    script = long_text
    monkeypatch.setattr(gem, "ask", lambda *a, **k: {"beats": [{"beat": "1", "text": long_text}]})
    said = []
    monkeypatch.setattr(gem, "say", lambda msg: said.append(msg))
    plan.split_into_beats(script, wpm=60)
    assert any("1" in msg for msg in said)


def test_split_into_beats_does_not_warn_when_under_the_ceiling(monkeypatch):
    script = "word word word"
    monkeypatch.setattr(gem, "ask", lambda *a, **k: {"beats": [{"beat": "1", "text": script}]})
    said = []
    monkeypatch.setattr(gem, "say", lambda msg: said.append(msg))
    plan.split_into_beats(script, wpm=130)
    assert said == []


# ------------------------------------------------------------ write_prompts --
def test_write_prompts_returns_a_prompt_per_beat(monkeypatch):
    beats = [{"beat": "1", "text": "a"}, {"beat": "2", "text": "b"}]
    monkeypatch.setattr(
        gem,
        "ask",
        lambda *a, **k: {
            "prompts": [
                {"beat": "1", "prompt": "prompt one"},
                {"beat": "2", "prompt": "prompt two"},
            ]
        },
    )
    prompts = plan.write_prompts(beats, style="some style")
    assert prompts == {"1": "prompt one", "2": "prompt two"}


def test_write_prompts_raises_when_a_beat_is_missing(monkeypatch):
    beats = [{"beat": "1", "text": "a"}, {"beat": "2", "text": "b"}]
    monkeypatch.setattr(
        gem, "ask", lambda *a, **k: {"prompts": [{"beat": "1", "prompt": "prompt one"}]}
    )
    with pytest.raises(ValueError, match=r"no prompt came back for beats \['2'\]"):
        plan.write_prompts(beats, style="some style")
