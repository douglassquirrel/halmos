#!/usr/bin/env python3
"""
halmos, step two: turn your recording and the pictures into a finished video.

  python3 2_make.py
  python3 2_make.py --project ~/videos/bees

Reads   : plan.json, corrections.txt, audio/narration.*, frames/, settings.json
Writes  : out/<name>.mp4   <- the finished video

All of the above are read from and written to --project (default: the
current directory, so running with no flags behaves exactly as before).

Takes about forty minutes, most of it waiting while the clips are generated.
Costs about £7. It prints a line as each clip finishes, so you can see it working.

Safe to re-run: clips that already exist are not paid for twice.
"""

import argparse
import glob
import json
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib import edit, gem, media, plan  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Turn a recording and the pictures from 1_plan.py into a finished video."
    )
    p.add_argument(
        "--project",
        default=".",
        help="project folder everything reads from and writes to (default: current directory)",
    )
    p.add_argument(
        "--style",
        help="path to your style block (default: whatever 1_plan.py used, from plan.json)",
    )
    return p.parse_args(argv)


def find_narration(project_dir):
    audio_dir = project_dir / "audio"
    for pat in ("narration.*", "Narration.*", "narration*"):
        for f in sorted(glob.glob(str(audio_dir / pat))):
            if not f.endswith((".json", ".txt")) and "clean" not in f:
                return f
    return None


def read_corrections(valid, project_dir):
    f = project_dir / "corrections.txt"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9\-]+)\s*[:\-]\s*(.+)$", line)
        if m and m.group(1) in valid:
            out[m.group(1)] = m.group(2).strip()
    return out


def main(argv=None):  # noqa: C901 - a linear script's main(), not a candidate for this pass's scope
    args = parse_args(argv)
    gem.need_package()
    media.need_ffmpeg()

    project_dir = pathlib.Path(args.project).expanduser().resolve()
    gem.PROJECT_DIR = project_dir

    s = gem.settings()
    plan_json = project_dir / "plan.json"
    if not plan_json.exists():
        sys.exit(f"No plan.json at {plan_json}. Run  python3 1_plan.py  first.")
    P = json.load(open(plan_json))

    style_path = (
        pathlib.Path(args.style).expanduser().resolve() if args.style else P.get("style_source")
    )
    style = gem.style_block(path=style_path)

    beats = P["beats"]
    prompts = {b["beat"]: b["prompt"] for b in beats}
    texts = {b["beat"]: b["text"] for b in beats}
    frames_dir = project_dir / "frames"
    work_dir = project_dir / "work"
    gen_dir = project_dir / "gen"
    out_dir = project_dir / "out"
    audio_dir = project_dir / "audio"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # ---- 1. corrections the human wrote ------------------------------------
    corr = read_corrections(set(prompts), project_dir)
    if corr:
        gem.say(f"Applying your corrections to {len(corr)} picture(s)...")
        items = [
            {"beat": b, "text": texts[b], "prompt": prompts[b], "note": n} for b, n in corr.items()
        ]
        new = plan.apply_corrections(items, style)
        for b, pr in new.items():
            prompts[b] = pr
            media.make_still(b, pr, style, outdir=str(frames_dir), force=True)
            gem.say(f"  {b} redrawn")
        for b in beats:
            b["prompt"] = prompts[b["beat"]]
        json.dump(P, open(plan_json, "w"), indent=2)
        media.contact_sheet(
            [b["beat"] for b in beats],
            outdir=str(frames_dir),
            dst=str(project_dir / "contact_sheet.png"),
            work=str(work_dir),
        )
        gem.say("  contact_sheet.png updated.")

    # ---- 2. the recording ---------------------------------------------------
    audio = find_narration(project_dir)
    if not audio:
        sys.exit(
            f"No recording found. Save it as  {audio_dir}/narration.m4a  "
            "(or .mp3 / .wav) and run this again."
        )
    gem.say(f"Reading your recording: {audio}")
    words_json = work_dir / "words.json"
    words = media.transcribe(audio, out=str(words_json))
    gem.say(f"  {len(words)} words heard.")

    cuts = media.find_retakes(words)
    if cuts:
        total = sum(c["end"] - c["start"] for c in cuts)
        gem.say(f"  found {len(cuts)} repeated take(s), removing {total:.1f}s")
        for c in cuts:
            gem.say(f'    dropping the earlier "{c["text"][:48]}..."')
        audio = media.cut_audio(
            audio, cuts, str(audio_dir / "narration_clean.m4a"), work=str(work_dir)
        )
        words = media.transcribe(audio, out=str(words_json))
        gem.say(f"  {len(words)} words after trimming.")

    shots = [{"beat": b["beat"], "text": b["text"]} for b in beats]
    try:
        shots = media.align(words, shots)
    except ValueError as e:
        sys.exit(f"\nCould not match your recording to the script.\n\n{e}\n")
    speech = sum(sh["dur"] for sh in shots)
    gem.say(f"  matched all {len(shots)} beats; {speech:.1f}s of speech.")

    res = s["resolution"]
    maxdur = max(media.ALLOWED_SECONDS[res])
    shots, made = media.split_long(words, shots, maxdur)
    if made:
        gem.say(f"  {len(made)} beat(s) were too long and were split: {', '.join(made)}")
        gem.say("  writing pictures for the new halves...")
        newbeats = [{"beat": sh["beat"], "text": sh["text"]} for sh in shots if sh["beat"] in made]
        extra = plan.write_prompts(newbeats, style)
        for sh in shots:
            if sh["beat"] in extra:
                prompts[sh["beat"]] = extra[sh["beat"]]
                media.make_still(sh["beat"], extra[sh["beat"]], style, outdir=str(frames_dir))

    # ---- 3. the clips -------------------------------------------------------
    def clip_path(beat):
        return gen_dir / f"beat_{beat}.mp4"

    need = [sh for sh in shots if not clip_path(sh["beat"]).exists()]
    est = len(need) * media.next_longest_available_clip(maxdur, res) * media.CLIP["lite"][1][res]
    gem.check_budget(est, s)
    gem.say(
        f"Generating {len(need)} clips. This takes about "
        f"{len(need) * 1.7:.0f} minutes - it is working even when quiet."
    )
    os.makedirs(gen_dir, exist_ok=True)
    done = len(shots) - len(need)
    quota_exhausted_models = set()  # models confirmed out of today's allowance
    for sh in shots:
        b = sh["beat"]
        dst = clip_path(b)
        if dst.exists():
            continue
        first_frame = str(frames_dir / f"{b}.png")
        made_it = None
        for m in s["clip_models"]:
            try:
                if m == "omni":
                    made_it, _ = media.make_clip_omni(
                        b, prompts.get(b, texts.get(b, "")), style, res, first_frame, str(gen_dir)
                    )
                else:
                    made_it, _ = media.make_clip_veo(
                        b,
                        prompts.get(b, texts.get(b, "")),
                        style,
                        sh["dur"],
                        m,
                        res,
                        first_frame,
                        str(gen_dir),
                    )
            except Exception as e:  # noqa: BLE001
                kind = gem.classify_error(e)
                if kind in ("bad_key", "billing", "model_not_found"):
                    # None of these are fixed by trying another model or
                    # shot - stop now rather than failing identically for
                    # every remaining clip.
                    sys.exit(
                        f"\nStopped at beat {b} ({done}/{len(shots)} clips already made, "
                        f"${gem.spent_so_far():.2f} spent so far).\n\n{gem.explain_error(e)}\n"
                    )
                if kind == "quota":
                    quota_exhausted_models.add(m)
                else:
                    gem.say(f"  {b}: {str(e)[:90]}")
                made_it = None
            if made_it:
                break
        done += 1
        gem.say(f"  [{done}/{len(shots)}] {b}" + ("" if made_it else "  NO CLIP"))
        if not made_it and quota_exhausted_models.issuperset(s["clip_models"]):
            # Every configured model is confirmed out of today's allowance -
            # the remaining shots would each fail the same way.
            sys.exit(
                f"\nStopped at beat {b} ({done - 1}/{len(shots)} clips already made, "
                f"${gem.spent_so_far():.2f} spent so far): every model in "
                f"clip_models ({', '.join(s['clip_models'])}) has used up today's "
                "allowance.\nNothing is lost - wait until tomorrow and run  "
                "python3 2_make.py  again; it carries on from where it stopped.\n"
            )
        time.sleep(12)

    missing = [sh["beat"] for sh in shots if not clip_path(sh["beat"]).exists()]
    if missing:
        sys.exit(
            f"\nCould not generate clips for: {', '.join(missing)}\n"
            f"${gem.spent_so_far():.2f} spent so far. This is almost always the "
            "daily limit. Nothing is lost - wait until tomorrow and run  "
            "python3 2_make.py  again; it carries on from where it stopped.\n"
        )

    # ---- 4. music -----------------------------------------------------------
    music_path = audio_dir / "music_bed.mp3"
    if not music_path.exists():
        gem.say("Writing music...")
        media.make_music(int(speech) + 3, s["music_mood"], s["music_instruments"], str(music_path))

    # ---- 5. the edit --------------------------------------------------------
    gem.say("Choosing the best few seconds of each clip...")
    for i, sh in enumerate(shots):
        f = str(clip_path(sh["beat"]))
        try:
            ip, rev, why = edit.choose_inpoint(f, sh["text"], sh["dur"], work=str(work_dir))
        except gem.FatalModelError as e:
            # Every remaining shot would fail the same way - stop now rather
            # than centring every one of the rest identically.
            sys.exit(
                f"\nStopped at beat {sh['beat']} ({i}/{len(shots)} in-points already chosen, "
                f"${gem.spent_so_far():.2f} spent so far).\n\n{e}\n"
            )
        except Exception as e:  # noqa: BLE001
            clip = float(media.probe(f) or 8.0)
            ip, rev, why = (
                max(0.0, (clip - sh["dur"]) / 2),
                False,
                f"COULD NOT CHECK ({str(e)[:40]}) - centred instead",
            )
        sh["in"], sh["in_note"] = round(ip, 2), why
        if rev:
            sh["reverse"] = True
        gem.say(f"  {sh['beat']}: from {ip:.1f}s{'  (reversed)' if rev else ''}  {why}")

    cfg = {
        "video": P["video"],
        "width": P["width"],
        "height": P["height"],
        "fps": P["fps"],
        "shots": shots,
        "sources": {sh["beat"]: {"file": str(clip_path(sh["beat"]))} for sh in shots},
        "narration": {"file": audio, "start": shots[0]["audio_start"]},
        "music": {"file": str(music_path), "gain_db": -18},
        "target_lufs": s["target_lufs"],
        "caption_font_family": s.get("caption_font_family"),
        "caption_font_file": s.get("caption_font_file"),
    }
    for sh in shots:
        sh["src"] = sh["beat"]
    json.dump(cfg, open(work_dir / "edit.json", "w"), indent=2)

    gem.say("Building the video...")
    final, total = edit.build(cfg, work=str(work_dir), out=str(out_dir))

    # ---- 6. checks ----------------------------------------------------------
    lufs = edit.loudness(final)
    ok_loud = lufs is not None and -16 <= lufs <= -12
    gem.say(f"Loudness: {lufs:.1f} LUFS" if lufs else "Loudness: could not measure")
    try:
        sheet, probs = edit.check_frames(final, shots, work=str(work_dir))
    except gem.FatalModelError as e:
        sheet, probs = None, []
        print(
            f"!! Could not check the finished frames for defects "
            f"(${gem.spent_so_far():.2f} spent so far): {e}"
        )

    print()
    gem.say(f"FINISHED:  {final}   ({total:.0f} seconds)")
    gem.say(f"Total spent on this video: ${gem.spent_so_far():.2f}")
    print()
    if not ok_loud:
        print("!! The sound level is outside the normal range. It may be too quiet")
        print("   or too loud on a phone. Re-record a little closer to the mic.")
    if probs:
        print("!! Check these shots - something may be wrong with them:")
        for p in probs:
            print(f"     {p['beat']}: {p['issue']}")
        print(f"   (see {sheet})")
    print("""
LAST STEP, AND IT IS NOT OPTIONAL
---------------------------------
Watch the whole video, with sound, before you put it anywhere.
Nothing automated can do this for you.
""")


if __name__ == "__main__":
    main()
