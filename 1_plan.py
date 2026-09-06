#!/usr/bin/env python3
"""
halmos, step one: turn your script into pictures to look at, and words to read aloud.

  python3 1_plan.py

Reads   : script.txt, style_block.txt, settings.json, ~/.config/halmos/key
Writes  : contact_sheet.png   <- LOOK AT THIS
          narration_script.txt <- READ THIS ALOUD AND RECORD IT
          corrections.txt      <- write here if any picture is wrong
          plan.json, frames/   <- working files; leave them alone

Costs about 40p and takes two minutes.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib import gem, media, plan  # noqa: E402


def main():  # noqa: C901 - a linear script's main(), not a candidate for this pass's scope
    gem.need_package()
    media.need_ffmpeg()
    s = gem.settings()
    style = gem.style_block()

    script_file = pathlib.Path("script.txt")
    if not script_file.exists():
        sys.exit("There is no script.txt in this folder. Put your script in it.")
    script = script_file.read_text().strip()
    if script.startswith("Replace this file"):
        sys.exit(
            "script.txt still has the placeholder text in it.\n"
            "Put your own script in it and run this again."
        )
    n = len(script.split())
    if n < 40:
        sys.exit(f"script.txt is only {n} words. That is too short to be a video.")
    if n > 400:
        sys.exit(
            f"script.txt is {n} words, which is over three minutes. Split it into separate videos."
        )

    gem.say(f"Script: {n} words, roughly {n / s['words_per_minute'] * 60:.0f} seconds spoken.")

    gem.say("Splitting it into beats...")
    beats = plan.split_into_beats(script, s["words_per_minute"])
    gem.say(f"  {len(beats)} beats.")

    gem.say("Writing a picture for each beat...")
    prompts = plan.write_prompts(beats, style)

    est = len(beats) * media.STILL_PRICE
    gem.check_budget(est, s)
    gem.say(f"Drawing {len(beats)} pictures (about ${est:.2f})...")
    os.makedirs("frames", exist_ok=True)
    for b in beats:
        p = media.make_still(b["beat"], prompts[b["beat"]], style)
        gem.say(f"  {b['beat']}" + ("" if p else "  FAILED - will retry once"))
        if not p:
            media.make_still(b["beat"], prompts[b["beat"]], style, force=True)

    gem.say("Checking each picture against its sentence...")
    fixed = 0
    for b in beats:
        img = f"frames/{b['beat']}.png"
        if not os.path.exists(img):
            continue
        try:
            v = plan.review_still(img, b["text"], prompts[b["beat"]], style)
        except Exception:
            continue
        if not v.get("ok") and v.get("revised_prompt"):
            why = "; ".join(v.get("problems", []))[:70]
            gem.say(f"  {b['beat']}: {why} - redrawing")
            prompts[b["beat"]] = v["revised_prompt"]
            media.make_still(b["beat"], prompts[b["beat"]], style, force=True)
            fixed += 1
    gem.say(f"  redrew {fixed} of {len(beats)}.")

    order = [b["beat"] for b in beats]
    media.contact_sheet(order)

    json.dump(
        {
            "video": s["video_name"],
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "words_per_minute": s["words_per_minute"],
            "beats": [
                {"beat": b["beat"], "text": b["text"], "prompt": prompts[b["beat"]]} for b in beats
            ],
        },
        open("plan.json", "w"),
        indent=2,
    )

    with open("narration_script.txt", "w") as f:
        f.write("READ THIS ALOUD AND RECORD IT\n")
        f.write("=" * 60 + "\n\n")
        f.write("Read the numbered lines below straight through, out loud.\n\n")
        f.write("  * PAUSE FOR ABOUT ONE SECOND between each numbered line.\n")
        f.write("    That is the only thing this asks of you.\n")
        f.write("  * Read at whatever pace feels natural.\n")
        f.write("  * If you fluff a line, pause and say it again. The repeat is\n")
        f.write("    removed automatically. You do not need to start over.\n")
        f.write("  * Speak close to the microphone, in a quiet room. A phone\n")
        f.write("    voice memo is fine.\n\n")
        f.write("Save the recording in this folder as:  audio/narration.m4a\n")
        f.write("(.mp3 or .wav are fine too - just keep the name 'narration'.)\n\n")
        f.write("=" * 60 + "\n\n")
        for b in beats:
            f.write(f"{b['beat']}.  {b['text']}\n\n")

    with open("corrections.txt", "w") as f:
        f.write("# CORRECTIONS - only if a picture is wrong\n#\n")
        f.write("# Open contact_sheet.png. Each picture has its beat name in the\n")
        f.write("# corner. If one is wrong, write a line here saying what is wrong\n")
        f.write("# with it, like this:\n#\n")
        f.write("#     3a: too abstract, show an actual open door\n")
        f.write("#     5b: there is writing on the sign\n#\n")
        f.write("# One line per picture. Say what is WRONG, not what to draw -\n")
        f.write("# the wording is rewritten for you.\n")
        f.write("# If every picture is fine, leave this file alone.\n#\n")
        f.write("# Your beats are: " + ", ".join(order) + "\n\n")

    print()
    gem.say(f"Done. Spent ${gem.spent_so_far():.2f} so far.")
    print("""
NOW DO THESE THREE THINGS
-------------------------

1. Open  contact_sheet.png  and look at the pictures.
   Any that are wrong? Write a line about each in  corrections.txt
   (If they all look fine, skip this.)

2. Open  narration_script.txt  and record yourself reading it.
   Save it as  audio/narration.m4a  in this folder.

3. Then run:   python3 2_make.py
""")


if __name__ == "__main__":
    main()
