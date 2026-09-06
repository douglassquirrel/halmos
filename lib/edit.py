#!/usr/bin/env python3
"""
The edit: choosing which seconds of each clip to keep, and building the file.

One judgement call in here (which window of the clip reads best) is made by a
vision model. Everything else is deterministic ffmpeg.
"""
import json, os, subprocess, sys, textwrap
from . import gem
from .media import run, probe

FUNCTION_WORDS = {"a", "an", "the", "in", "of", "to", "and", "with", "that", "its",
                  "for", "from", "by", "on", "at", "as", "it", "is", "was", "were",
                  "be", "been", "or", "but", "so", "then", "this", "these"}


# ------------------------------------------------------------- in-points -----
INPOINT_RULES = """You are choosing which part of a generated video clip to keep.

The clip is %(clip).1f seconds long. Only %(dur).1f seconds of it will be used,
starting at a point you choose. The picture below shows %(n)d frames sampled
evenly across the whole clip, left to right, at these times in seconds: %(times)s

The kept section must contain the moment where the action READS most clearly for
this sentence: "%(text)s"

Also watch for, and cut around if you can:
- photographic human hands or arms entering the frame
- the subject leaving frame, or the picture going empty
- the first second or two, which is often just the scene sitting still

And tell me: does the action appear to run BACKWARDS relative to the sentence?
For instance the sentence says something falls or collapses, but across the
frames it rises or assembles instead.

Return JSON only:
{"in": <seconds, 0 to %(maxin).2f>, "reverse": true/false, "why": "<12 words>"}
"""


def choose_inpoint(clip_path, beat_text, dur, work="work"):
    clip = float(probe(clip_path) or 8.0)
    maxin = max(0.0, clip - dur)
    n = 6
    times = [clip * (i + 0.5) / n for i in range(n)]
    # ffprobe returns one line per stream; the audio stream's rate is "0/0", so
    # take the first line only and fall back to 24 if it is not a real rate.
    raw = (probe(clip_path, "stream=r_frame_rate").splitlines() or ["24/1"])[0]
    try:
        num, den = raw.split("/")
        fps = float(num) / (float(den) or 1)
        if fps <= 0:
            fps = 24.0
    except (ValueError, ZeroDivisionError):
        fps = 24.0
    sel = "+".join(f"eq(n\\,{int(round(t * fps))})" for t in times)
    strip = f"{work}/_strip.png"
    os.makedirs(work, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-vf",
         f"select='{sel}',scale=180:-1,tile={n}x1", "-frames:v", "1", strip])
    ans = gem.ask(INPOINT_RULES % {
        "clip": clip, "dur": dur, "n": n, "maxin": maxin,
        "times": ", ".join(f"{t:.1f}" for t in times), "text": beat_text},
        images=[strip])
    val = float(ans.get("in", maxin / 2))
    return (max(0.0, min(maxin, val)), bool(ans.get("reverse", False)),
            str(ans.get("why", ""))[:90])


# ----------------------------------------------------------- verification ----
CHECK_RULES = """You are checking finished frames from a short video for defects.

The picture shows one frame from each shot, in order. For EACH numbered frame,
report only real problems:
- any text on any object: words, letters, numbers, labels, signs, writing
- photographic human hands, arms or bodies
- the frame being empty, black, or obviously broken

Return JSON only: {"problems": [{"frame": <1-based number>, "issue": "..."}]}
Return an empty list if there are none. Burned-in captions at the bottom of the
frame are expected and are NOT a problem.
"""


def check_frames(video, shots, work="work"):
    t, times = 0.0, []
    for s in shots:
        times.append(t + s["dur"] * 0.6); t += s["dur"]
    sel = "+".join(f"eq(n\\,{int(round(x * 30))})" for x in times)
    cols = 6
    rows = (len(times) + cols - 1) // cols
    sheet = f"{work}/_check.png"
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf",
         f"select='{sel}',scale=190:-1,tile={cols}x{rows}", "-frames:v", "1", sheet])
    try:
        out = gem.ask(CHECK_RULES, images=[sheet])
        probs = out.get("problems", [])
    except Exception:
        return sheet, []
    named = []
    for p in probs:
        i = int(p.get("frame", 0)) - 1
        if 0 <= i < len(shots):
            named.append({"beat": shots[i]["beat"], "issue": p.get("issue", "")})
    return sheet, named


# ---------------------------------------------------------------- build ------
def _ass_time(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _chunks(text, per=6):
    words, out, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= per and w.lower().strip(".,;:") not in FUNCTION_WORDS:
            out.append(" ".join(cur)); cur = []
    if cur:
        if out and len(cur) < 3:
            out[-1] += " " + " ".join(cur)
        else:
            out.append(" ".join(cur))
    return out


def build(cfg, work="work", out="out"):
    os.makedirs(work, exist_ok=True); os.makedirs(out, exist_ok=True)
    W, H, FPS = cfg["width"], cfg["height"], cfg["fps"]
    shots = cfg["shots"]
    family = cfg.get("caption_font_family") or "DejaVu Sans"
    fontdir = os.path.dirname(cfg.get("caption_font_file") or "") or "/usr/share/fonts"

    parts, meas = [], []
    for i, sh in enumerate(shots):
        src = cfg["sources"][sh["src"]]["file"]
        d = sh["dur"]
        dst = f"{work}/s{i:02d}.mp4"
        ss = float(sh.get("in", 0))
        rev = bool(sh.get("reverse"))
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p"
        args = ["ffmpeg", "-y", "-v", "error"]
        if rev:
            vf = "reverse," + vf + f",trim=start={ss}:duration={d},setpts=PTS-STARTPTS"
        elif ss:
            args += ["-ss", str(ss)]
        args += ["-i", src, "-vf", vf, "-r", str(FPS),
                 "-frames:v", str(int(round(d * FPS))),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-an", dst]
        run(args, f"cutting shot {sh['beat']}")
        parts.append(dst)
        meas.append(float(probe(dst)))

    # captions
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{family},64,&H00FFFFFF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,1,5,3,2,90,90,300,1
Style: Hook,{family},80,&H00FFFFFF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,1,6,4,2,80,80,430,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines, t = [], 0.0
    for k, sh in enumerate(shots):
        d = meas[k]
        cs = _chunks(sh["text"])
        wt = [len(c.split()) for c in cs]; tot = sum(wt) or 1
        style = "Hook" if k == 0 else "Cap"
        ct = t
        for c, n in zip(cs, wt):
            cd = d * n / tot
            txt = c.replace("\n", " ")
            wrapped = "\\N".join(textwrap.wrap(txt, 26)) if len(txt) > 26 else txt
            lines.append(f"Dialogue: 0,{_ass_time(ct)},{_ass_time(ct+cd)},{style},,0,0,0,,{wrapped}")
            ct += cd
        t += d
    open(f"{work}/captions.ass", "w").write(head + "\n".join(lines) + "\n")
    total = t

    with open(f"{work}/concat.txt", "w") as f:
        for p in parts:
            f.write(f"file '{os.path.basename(p)}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", f"{work}/concat.txt", "-c", "copy", f"{work}/joined.mp4"], "joining")

    nar = cfg.get("narration"); mus = cfg.get("music")
    target = cfg.get("target_lufs", -14)
    FMT = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    fade = f",fade=t=out:st={max(0,total-1.2):.2f}:d=1.2"
    final = f"{out}/{cfg['video']}.mp4"
    args = ["ffmpeg", "-y", "-v", "error", "-i", f"{work}/joined.mp4"]

    if nar and os.path.exists(nar["file"]):
        args += ["-ss", str(nar.get("start", 0)), "-i", nar["file"]]
        use_music = bool(mus and os.path.exists(mus.get("file", "")))
        if use_music:
            args += ["-i", mus["file"]]
            g = mus.get("gain_db", -18)
            af = (f"[0:v]ass={work}/captions.ass:fontsdir={fontdir}{fade}[vout];"
                  f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,{FMT},asplit=2[voice][key];"
                  f"[2:a]loudnorm=I=-16:TP=-1.5,{FMT},volume={g}dB,afade=t=in:d=2,"
                  f"afade=t=out:st={max(0,total-3):.2f}:d=3[bed];"
                  f"[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=15:"
                  f"release=450:makeup=1[duck];"
                  f"[voice][duck]amix=inputs=2:duration=first:normalize=0,"
                  f"loudnorm=I={target}:TP=-1:LRA=11,{FMT},"
                  f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                  f"afade=t=out:st={max(0,total-0.8):.2f}:d=0.8[aout]")
            args += ["-filter_complex", af, "-map", "[vout]", "-map", "[aout]"]
        else:
            args += ["-vf", f"ass={work}/captions.ass:fontsdir={fontdir}{fade}",
                     "-af", f"loudnorm=I={target}:TP=-1:LRA=11,{FMT},"
                            f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                            f"afade=t=out:st={max(0,total-0.8):.2f}:d=0.8"]
    else:
        args += ["-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=48000:cl=stereo",
                 "-vf", f"ass={work}/captions.ass:fontsdir={fontdir}{fade}"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", final]
    run(args, "final mux")
    return final, total


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128", "-f", "null", "/dev/null"],
                       capture_output=True, text=True)
    for line in p.stderr.splitlines():
        s = line.strip()
        if s.startswith("I:") and "LUFS" in s:
            try:
                return float(s.split()[1])
            except (IndexError, ValueError):
                pass
    return None
