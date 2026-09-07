#!/usr/bin/env python3
"""
halmos, step one: turn your script into pictures to look at, and words to read aloud.

  python3 1_plan.py
  python3 1_plan.py --script ~/videos/bees/script.txt \
                     --style  ~/videos/house-style.txt --out ~/videos/bees

Reads   : script.txt, style_block.txt, settings.json, ~/.config/halmos/key
Writes  : contact_sheet.png   <- LOOK AT THIS
          narration_script.txt <- READ THIS ALOUD AND RECORD IT
          corrections.txt      <- write here if any picture is wrong
          plan.json, frames/   <- working files; leave them alone

All of the above are read from and written to --out (default: the current
directory, so running with no flags behaves exactly as before).

Costs about 40p and takes two minutes.
"""

import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib import gem, media, plan  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Turn a script into pictures to look at and words to read aloud."
    )
    p.add_argument("--script", help="path to your script (default: script.txt inside --out)")
    p.add_argument(
        "--style", help="path to your style block (default: style_block.txt inside --out)"
    )
    p.add_argument(
        "--out",
        default=".",
        help="project folder everything reads from and writes to (default: current directory)",
    )
    return p.parse_args(argv)


def main(argv=None):  # noqa: C901 - a linear script's main(), not a candidate for this pass's scope
    args = parse_args(argv)
    gem.need_package()
    media.need_ffmpeg()

    project_dir = pathlib.Path(args.out).expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    gem.PROJECT_DIR = project_dir

    s = gem.settings()
    style_path = (
        pathlib.Path(args.style).expanduser().resolve()
        if args.style
        else (project_dir / "style_block.txt")
    )
    style = gem.style_block(path=style_path)

    script_file = (
        pathlib.Path(args.script).expanduser().resolve()
        if args.script
        else (project_dir / "script.txt")
    )
    if not script_file.exists():
        sys.exit(f"There is no script at {script_file}. Put your script there.")
    script = script_file.read_text().strip()
    if script.startswith("Replace this file"):
        sys.exit(
            f"{script_file} still has the placeholder text in it.\n"
            "Put your own script in it and run this again."
        )
    n = len(script.split())
    if n < 40:
        sys.exit(f"{script_file} is only {n} words. That is too short to be a video.")
    if n > 400:
        sys.exit(
            f"{script_file} is {n} words, which is over three minutes. "
            "Split it into separate videos."
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
    frames_dir = project_dir / "frames"
    os.makedirs(frames_dir, exist_ok=True)
    for i, b in enumerate(beats):
        try:
            p = media.make_still(b["beat"], prompts[b["beat"]], style, outdir=str(frames_dir))
            gem.say(f"  {b['beat']}" + ("" if p else "  FAILED - will retry once"))
            if not p:
                media.make_still(
                    b["beat"], prompts[b["beat"]], style, outdir=str(frames_dir), force=True
                )
        except Exception as e:  # noqa: BLE001
            if gem.classify_error(e) in ("bad_key", "billing", "quota", "model_not_found"):
                # Every remaining picture would fail the same way - stop now
                # rather than working through the rest identically.
                sys.exit(
                    f"\nStopped at beat {b['beat']} ({i}/{len(beats)} pictures already drawn, "
                    f"${gem.spent_so_far():.2f} spent so far).\n\n{gem.explain_error(e)}\n"
                )
            gem.say(f"  {b['beat']}  FAILED ({str(e)[:60]})")

    missing = [b["beat"] for b in beats if not (frames_dir / f"{b['beat']}.png").exists()]
    if missing:
        # Matches 2_make.py's own clip loop, which already stops if ANY clip
        # is missing, not only if all of them are - a single missing beat
        # has no way to be flagged via corrections.txt (that only comments
        # on a picture that exists and is wrong, not one that's silently
        # absent), and every downstream step assumes every beat has one.
        # Cheap to re-run either way: make_still() skips beats that already
        # have a picture.
        sys.exit(
            f"\nSTOPPING: could not generate a picture for: {', '.join(missing)}\n"
            f"(${gem.spent_so_far():.2f} spent so far). See the errors above for "
            "why each one failed.\n"
            "Nothing else was written - fix whatever they're pointing at and run "
            "python3 1_plan.py again; it only retries what's missing.\n"
        )

    gem.say("Checking each picture against its sentence...")
    fixed = 0
    for i, b in enumerate(beats):
        img = frames_dir / f"{b['beat']}.png"
        if not img.exists():
            continue
        try:
            v = plan.review_still(str(img), b["text"], prompts[b["beat"]], style)
        except gem.FatalModelError as e:
            # Every remaining review would fail the same way - stop now
            # rather than silently skipping the rest one by one.
            sys.exit(
                f"\nStopped reviewing at beat {b['beat']} ({i}/{len(beats)} beats checked, "
                f"${gem.spent_so_far():.2f} spent so far).\n\n{e}\n"
            )
        except Exception:
            v = None
        if v is not None and not v.get("ok") and v.get("revised_prompt"):
            why = "; ".join(v.get("problems", []))[:70]
            gem.say(f"  {b['beat']}: {why} - redrawing")
            prompts[b["beat"]] = v["revised_prompt"]
            media.make_still(
                b["beat"], prompts[b["beat"]], style, outdir=str(frames_dir), force=True
            )
            fixed += 1
        if i < len(beats) - 1:
            # One gem.ask() call per beat, back to back, otherwise trips the
            # ~2/minute rate limit near the end of a long loop - see
            # gem.TEXT_MODEL_PACING_SECONDS. Applies whether the call
            # succeeded or failed non-fatally; either way it counted against
            # the limit.
            time.sleep(gem.TEXT_MODEL_PACING_SECONDS)
    gem.say(f"  redrew {fixed} of {len(beats)}.")

    order = [b["beat"] for b in beats]
    contact_sheet = project_dir / "contact_sheet.png"
    media.contact_sheet(
        order, outdir=str(frames_dir), dst=str(contact_sheet), work=str(project_dir / "work")
    )

    json.dump(
        {
            "video": s["video_name"],
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "words_per_minute": s["words_per_minute"],
            # so 2_make.py finds the same style without needing --style again -
            # a style file shared across several projects only has to be named once.
            "style_source": str(style_path),
            "beats": [
                {"beat": b["beat"], "text": b["text"], "prompt": prompts[b["beat"]]} for b in beats
            ],
        },
        open(project_dir / "plan.json", "w"),
        indent=2,
    )

    narration_script = project_dir / "narration_script.txt"
    narration_audio_dir = project_dir / "audio"
    with open(narration_script, "w") as f:
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
        f.write(f"Save the recording as:  {narration_audio_dir}/narration.m4a\n")
        f.write("(.mp3 or .wav are fine too - just keep the name 'narration'.)\n\n")
        f.write("=" * 60 + "\n\n")
        for b in beats:
            f.write(f"{b['beat']}.  {b['text']}\n\n")

    corrections = project_dir / "corrections.txt"
    with open(corrections, "w") as f:
        f.write("# CORRECTIONS - only if a picture is wrong\n#\n")
        f.write(f"# Open {contact_sheet}. Each picture has its beat name in the\n")
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
    out_flag = "" if project_dir == pathlib.Path.cwd() else f" --project {project_dir}"
    print(f"""
NOW DO THESE THREE THINGS
-------------------------

1. Open  {contact_sheet}  and look at the pictures.
   Any that are wrong? Write a line about each in  {corrections}
   (If they all look fine, skip this.)

2. Open  {narration_script}  and record yourself reading it.
   Save it as  {narration_audio_dir}/narration.m4a

3. Then run:   python3 2_make.py{out_flag}
""")


if __name__ == "__main__":
    main()
