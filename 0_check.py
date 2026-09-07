#!/usr/bin/env python3
"""
halmos, step zero: check your computer has everything halmos needs.

  python3 0_check.py

Checks the google-genai package, ffmpeg/ffprobe, the caption-rendering and
labelling libraries 2_make.py's final steps need, and that an API key is
where halmos looks for one. Prints every problem found, not just the first,
so you can fix everything in one pass instead of one surprise at a time.

Costs nothing and touches no network - it only looks at what is already on
this computer. It does not check whether your key actually works; that is
free to find out anyway, since an invalid key fails on the very first call
1_plan.py makes, before anything is charged.

Run this once after "Before you start" in README.md, and again any time
something halmos needs might have changed underneath it.
"""

import pathlib
import sys
from shutil import which

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib import gem, media  # noqa: E402


def main():
    problems = []

    ffmpeg_ok, ffmpeg_detail = media.ffmpeg_diagnostic()
    if which("ffmpeg") and which("ffprobe") and ffmpeg_ok:
        print("OK       ffmpeg and ffprobe are installed and run correctly")
    elif which("ffmpeg") and not ffmpeg_ok:
        # A binary on PATH that crashes is a different, more confusing
        # problem than a missing one - found live, 2026-09-07: ffmpeg-full
        # is keg-only (Homebrew deliberately doesn't put it on PATH, since
        # it conflicts with plain ffmpeg's binaries), so installing it is
        # not enough on its own without the PATH export its own install
        # caveats print. Naming the real crash (not a generic guess) is
        # what actually let that get diagnosed and fixed.
        problems.append(
            f"ffmpeg is on your PATH but crashes when run: {ffmpeg_detail}\n"
            "         This usually means ffmpeg-full is installed but not on your\n"
            "         PATH yet (it's a Homebrew 'keg-only' formula, so brew install\n"
            "         alone doesn't put it there) - add it with:\n"
            "             echo 'export PATH=\"/opt/homebrew/opt/ffmpeg-full/bin:$PATH\"' "
            ">> ~/.zshrc\n"
            "         then open a new terminal window and run this check again."
        )
        print("BROKEN   ffmpeg is on your PATH but does not run")
    else:
        problems.append("ffmpeg is not installed - see README.md, 'Before you start'.")
        print("MISSING  ffmpeg and/or ffprobe")

    # The two library checks below need ffmpeg to actually run, not just be
    # present - has_ffmpeg_filter() already returns False safely either
    # way, but a MISSING line naming the wrong cause would be confusing, so
    # skip straight past them unless ffmpeg_ok is true.
    if ffmpeg_ok:
        if media.has_ffmpeg_filter("ass"):
            print("OK       ffmpeg has the caption-rendering library (libass)")
        else:
            problems.append(
                "ffmpeg was built without libass, so 2_make.py's caption burn-in\n"
                "         will fail at its very last step, after everything else is\n"
                "         already done. On a Mac: brew install ffmpeg-full\n"
                "         (see README.md, 'Before you start', for other systems).\n"
                "         Check for yourself with:  ffmpeg -filters | grep -E 'ass|drawtext'"
            )
            print("MISSING  the caption-rendering library (libass)")

        if media.has_ffmpeg_filter("drawtext"):
            print("OK       ffmpeg has the label-drawing library (drawtext)")
        else:
            problems.append(
                "ffmpeg was built without drawtext, so 1_plan.py's contact sheet\n"
                "         won't show which picture is which. On a Mac:\n"
                "         brew install ffmpeg-full (see README.md for other systems).\n"
                "         Check for yourself with:  ffmpeg -filters | grep -E 'ass|drawtext'"
            )
            print("MISSING  the label-drawing library (drawtext)")

    try:
        import google.genai  # noqa: F401

        print("OK       the google-genai package is installed")
    except ImportError:
        problems.append("The google-genai package is not installed. Run:  pip install google-genai")
        print("MISSING  the google-genai package")

    try:
        gem.api_key()
        print("OK       an API key was found")
    except SystemExit as e:
        problems.append(str(e))
        print("MISSING  an API key")

    print()
    if not problems:
        print("Everything halmos needs is in place. Run  python3 1_plan.py  when ready.")
        return
    print(f"{len(problems)} problem(s) found - fix these before running 1_plan.py:\n")
    for i, p in enumerate(problems, 1):
        print(f"{i}. {p}\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
