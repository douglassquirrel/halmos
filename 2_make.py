#!/usr/bin/env python3
"""
STEP TWO. Turn your recording and the pictures into a finished video.

  python3 2_make.py

Reads   : plan.json, corrections.txt, audio/narration.*, frames/, settings.json
Writes  : out/<name>.mp4   <- the finished video

Takes about forty minutes, most of it waiting while the clips are generated.
Costs about £7. It prints a line as each clip finishes, so you can see it working.

Safe to re-run: clips that already exist are not paid for twice.
"""
import glob, json, os, pathlib, re, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib import gem, plan, media, edit                            # noqa: E402


def find_narration():
    for pat in ("audio/narration.*", "audio/Narration.*", "audio/narration*"):
        for f in sorted(glob.glob(pat)):
            if not f.endswith((".json", ".txt")) and "clean" not in f:
                return f
    return None


def read_corrections(valid):
    f = pathlib.Path("corrections.txt")
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


def main():
    gem.need_package()
    media.need_ffmpeg()
    s = gem.settings()
    style = gem.style_block()
    if not os.path.exists("plan.json"):
        sys.exit("No plan.json here. Run  python3 1_plan.py  first.")
    P = json.load(open("plan.json"))
    beats = P["beats"]
    prompts = {b["beat"]: b["prompt"] for b in beats}
    texts = {b["beat"]: b["text"] for b in beats}
    os.makedirs("work", exist_ok=True); os.makedirs("audio", exist_ok=True)

    # ---- 1. corrections the human wrote ------------------------------------
    corr = read_corrections(set(prompts))
    if corr:
        gem.say(f"Applying your corrections to {len(corr)} picture(s)...")
        items = [{"beat": b, "text": texts[b], "prompt": prompts[b], "note": n}
                 for b, n in corr.items()]
        new = plan.apply_corrections(items, style)
        for b, pr in new.items():
            prompts[b] = pr
            media.make_still(b, pr, style, force=True)
            gem.say(f"  {b} redrawn")
        for b in beats:
            b["prompt"] = prompts[b["beat"]]
        json.dump(P, open("plan.json", "w"), indent=2)
        media.contact_sheet([b["beat"] for b in beats])
        gem.say("  contact_sheet.png updated.")

    # ---- 2. the recording ---------------------------------------------------
    audio = find_narration()
    if not audio:
        sys.exit("No recording found. Save it as  audio/narration.m4a  "
                 "(or .mp3 / .wav) and run this again.")
    gem.say(f"Reading your recording: {audio}")
    words = media.transcribe(audio)
    gem.say(f"  {len(words)} words heard.")

    cuts = media.find_retakes(words)
    if cuts:
        total = sum(c["end"] - c["start"] for c in cuts)
        gem.say(f"  found {len(cuts)} repeated take(s), removing {total:.1f}s")
        for c in cuts:
            gem.say(f'    dropping the earlier "{c["text"][:48]}..."')
        audio = media.cut_audio(audio, cuts, "audio/narration_clean.m4a")
        words = media.transcribe(audio)
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
        newbeats = [{"beat": sh["beat"], "text": sh["text"]} for sh in shots
                    if sh["beat"] in made]
        extra = plan.write_prompts(newbeats, style)
        for sh in shots:
            if sh["beat"] in extra:
                prompts[sh["beat"]] = extra[sh["beat"]]
                media.make_still(sh["beat"], extra[sh["beat"]], style)

    # ---- 3. the clips -------------------------------------------------------
    need = [sh for sh in shots if not os.path.exists(f"gen/beat_{sh['beat']}.mp4")]
    est = len(need) * media.purchased(maxdur, res) * media.CLIP["lite"][1][res]
    gem.check_budget(est, s)
    gem.say(f"Generating {len(need)} clips. This takes about "
            f"{len(need) * 1.7:.0f} minutes - it is working even when quiet.")
    os.makedirs("gen", exist_ok=True)
    done = len(shots) - len(need)
    for sh in shots:
        b = sh["beat"]
        dst = f"gen/beat_{b}.mp4"
        if os.path.exists(dst):
            continue
        made_it = None
        for m in s["clip_models"]:
            try:
                if m == "omni":
                    made_it, _ = media.make_clip_omni(
                        b, prompts.get(b, texts.get(b, "")), style, res,
                        f"frames/{b}.png", "gen")
                else:
                    made_it, _ = media.make_clip_veo(
                        b, prompts.get(b, texts.get(b, "")), style, sh["dur"],
                        m, res, f"frames/{b}.png", "gen")
            except Exception as e:                                # noqa: BLE001
                if "RESOURCE_EXHAUSTED" not in str(e) and "429" not in str(e):
                    gem.say(f"  {b}: {str(e)[:90]}")
                made_it = None
            if made_it:
                break
        done += 1
        gem.say(f"  [{done}/{len(shots)}] {b}" + ("" if made_it else "  NO CLIP"))
        time.sleep(12)

    missing = [sh["beat"] for sh in shots if not os.path.exists(f"gen/beat_{sh['beat']}.mp4")]
    if missing:
        sys.exit(f"\nCould not generate clips for: {', '.join(missing)}\n"
                 "This is almost always the daily limit. Nothing is lost - wait "
                 "until tomorrow and run  python3 2_make.py  again; it carries on "
                 "from where it stopped.\n")

    # ---- 4. music -----------------------------------------------------------
    if not os.path.exists("audio/music_bed.mp3"):
        gem.say("Writing music...")
        media.make_music(int(speech) + 3, s["music_mood"], s["music_instruments"])

    # ---- 5. the edit --------------------------------------------------------
    gem.say("Choosing the best few seconds of each clip...")
    for sh in shots:
        f = f"gen/beat_{sh['beat']}.mp4"
        try:
            ip, rev, why = edit.choose_inpoint(f, sh["text"], sh["dur"])
        except Exception as e:                                    # noqa: BLE001
            clip = float(media.probe(f) or 8.0)
            ip, rev, why = (max(0.0, (clip - sh["dur"]) / 2), False,
                            f"COULD NOT CHECK ({str(e)[:40]}) - centred instead")
        sh["in"], sh["in_note"] = round(ip, 2), why
        if rev:
            sh["reverse"] = True
        gem.say(f"  {sh['beat']}: from {ip:.1f}s{'  (reversed)' if rev else ''}  {why}")

    cfg = {"video": P["video"], "width": P["width"], "height": P["height"],
           "fps": P["fps"], "shots": shots,
           "sources": {sh["beat"]: {"file": f"gen/beat_{sh['beat']}.mp4"} for sh in shots},
           "narration": {"file": audio, "start": shots[0]["audio_start"]},
           "music": {"file": "audio/music_bed.mp3", "gain_db": -18},
           "target_lufs": s["target_lufs"],
           "caption_font_family": s.get("caption_font_family"),
           "caption_font_file": s.get("caption_font_file")}
    for sh in shots:
        sh["src"] = sh["beat"]
    json.dump(cfg, open("work/edit.json", "w"), indent=2)

    gem.say("Building the video...")
    final, total = edit.build(cfg)

    # ---- 6. checks ----------------------------------------------------------
    lufs = edit.loudness(final)
    ok_loud = lufs is not None and -16 <= lufs <= -12
    gem.say(f"Loudness: {lufs:.1f} LUFS" if lufs else "Loudness: could not measure")
    sheet, probs = edit.check_frames(final, shots)

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
