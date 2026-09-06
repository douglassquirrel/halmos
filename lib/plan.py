#!/usr/bin/env python3
# halmos - MIT licence, see LICENSE
"""
The judgement half: turning a script into beats, and beats into shot prompts.

This is the part that used to need a person thinking. It is now two calls to a
Gemini text model with carefully written instructions, plus a vision call that
marks its own homework by looking at the pictures it asked for.
"""
import json, pathlib, re
from . import gem


# --------------------------------------------------------------- beats -------
BEAT_RULES = """You are preparing a short vertical explainer video.

Split the script below into BEATS. A beat is one clause or short sentence: one
thought, which will get one picture.

Hard rules:
- Every word of the script must appear in exactly one beat, in the original
  order, with the original wording and punctuation. Do not rewrite, summarise,
  correct or reorder anything. You are only inserting split points.
- Each beat must be SHORT ENOUGH TO SAY IN UNDER 8 SECONDS at %(wpm)d words per
  minute. That is about %(maxwords)d words. This is a hard technical ceiling.
- Aim for roughly one beat per 10 to 14 words of script: about 8 beats for
  100 words, 12 for 150. Fewer, longer beats read better than many short
  ones - each beat is a cut, and too many cuts is choppy. Never fewer
  than 6 or more than 16.
- Split at natural breath points: clause boundaries, commas, dashes, "and", "but".
- The first beat is the hook. Keep it short and punchy.

Name the beats "1", "2a", "2b", "3a" and so on: a number for each sentence or
idea, a letter for each clause within it, so related beats are visibly related.

Return JSON only:
{"beats": [{"beat": "1", "text": "..."}, {"beat": "2a", "text": "..."}]}
"""

PROMPT_RULES = """You are writing image prompts for a short vertical explainer video.

You will be given the video's VISUAL STYLE and a list of BEATS. Write one prompt
per beat describing what the picture shows.

THE ONE RULE THAT MATTERS: the picture must say what the sentence says — every
part of it. Take each sentence apart into its claims and make sure the described
picture carries each one. A picture that is merely pretty, or merely related to
the topic, is a failure.

Worked example of the standard. For the sentence "Computers that program
themselves - in 1961!" there are three claims: it is a COMPUTER, it is 1961, and
it does it ITSELF. A machine with shapes moving on it carries one of the three.
A machine with tape reels, banks of switches and punched cards carries the first
two. Cards lifting out of that machine's OWN panel and settling back in a new
order, with nothing else entering the frame and nobody present, carries all three.

How to write them:
- DESCRIBE OBJECTS AND MOVEMENTS, NOT CONCEPTS. "A block hops down a curve one
  step at a time, each step shorter than the last, and comes to rest on a marked
  cross" works. "Gradient descent" does not. If a beat is abstract, find a
  physical comparison: three shapes where the joined one grows visibly taller
  than the two beside it.
- ONE clear action per shot, that a viewer could describe afterwards.
- Say what must NOT be in frame when it matters. Explicit prohibitions work far
  better on these models than richer description. If a shot could be
  misinterpreted as somebody else acting on the subject, say "nothing enters or
  leaves the frame, nobody present".
- Do NOT repeat the style description - it is added automatically. Describe only
  what is in this particular shot.
- Vary the shots. If several beats would produce similar-looking pictures, change
  the objects so each shot means something specific.
- Never ask for text, words, numbers or labels in the picture.
- 40 to 70 words each.

Return JSON only:
{"prompts": [{"beat": "1", "prompt": "..."}, ...]}
"""


def split_into_beats(script_text, wpm):
    maxwords = int(8 * wpm / 60)
    out = gem.ask(
        (BEAT_RULES % {"wpm": wpm, "maxwords": maxwords})
        + "\n\nSCRIPT:\n" + script_text.strip())
    beats = out["beats"]

    # Trust but verify: every word must survive, in order.
    def words(s):
        return re.findall(r"[a-z0-9']+", s.lower())
    if words(" ".join(b["text"] for b in beats)) != words(script_text):
        raise ValueError(
            "The beat split changed the wording of your script. Not continuing.\n"
            "This is a model error - just run the same command again.")
    long = [b["beat"] for b in beats if len(b["text"].split()) > maxwords + 4]
    if long:
        gem.say(f"note: beats {long} may be over 8s; they will be split "
                f"automatically after you record.")
    return beats


def write_prompts(beats, style):
    payload = json.dumps([{"beat": b["beat"], "text": b["text"]} for b in beats],
                         indent=1)
    out = gem.ask(PROMPT_RULES + "\n\nVISUAL STYLE:\n" + style +
                  "\n\nBEATS:\n" + payload)
    got = {p["beat"]: p["prompt"] for p in out["prompts"]}
    missing = [b["beat"] for b in beats if b["beat"] not in got]
    if missing:
        raise ValueError(f"no prompt came back for beats {missing}; run again")
    return got


# --------------------------------------------------------------- review ------
REVIEW_RULES = """You are checking one still image against the sentence it must
illustrate, for a short explainer video.

Answer these, strictly:
1. Does the picture carry EVERY claim in the sentence? Break the sentence into
   its claims and check each one.
2. Is there ANY text in the picture - words, letters, numbers, labels, signs,
   writing on any object? Even small or partial text counts.
3. Is it ONE single image, or has it come back as a grid of panels, a split
   screen, or repeated copies of the subject?
4. Are there photographic human hands, arms or bodies?
5. Does it match the stated visual style?

Return JSON only:
{"ok": true/false,
 "problems": ["short description", ...],
 "revised_prompt": "..."}

Set ok=false if ANY of 2, 3 or 4 is wrong, or if the picture misses a claim in
the sentence. When ok=false, write revised_prompt: a full replacement prompt that
fixes the problem, keeping everything that worked. Prefer adding an explicit
prohibition over describing harder. When ok=true, set revised_prompt to "".
"""


def review_still(image_path, beat_text, prompt, style):
    return gem.ask(
        REVIEW_RULES + "\n\nVISUAL STYLE:\n" + style +
        "\n\nSENTENCE THE PICTURE MUST CARRY:\n" + beat_text +
        "\n\nPROMPT THAT PRODUCED IT:\n" + prompt,
        images=[image_path])


# ------------------------------------------------------- user corrections ----
CORRECTION_RULES = """You are revising image prompts for a short explainer video
after a human reviewed the pictures.

For each beat below you are given: the sentence, the prompt that produced the
current picture, and the human's note about what is wrong. Write a replacement
prompt that addresses the note.

Keep everything that was working. Do not repeat the style description. Prefer
explicit prohibitions over longer description. Describe objects and movements,
not concepts.

Return JSON only: {"prompts": [{"beat": "...", "prompt": "..."}]}
"""


def apply_corrections(items, style):
    """items: [{beat, text, prompt, note}] -> {beat: new_prompt}"""
    out = gem.ask(CORRECTION_RULES + "\n\nVISUAL STYLE:\n" + style +
                  "\n\nBEATS TO REVISE:\n" + json.dumps(items, indent=1))
    return {p["beat"]: p["prompt"] for p in out["prompts"]}
