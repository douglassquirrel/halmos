#!/usr/bin/env python3
"""
The mechanical half: pictures, clips, audio, and the finished file.

Nothing in here makes a judgement. Same inputs, same outputs.
"""
import base64, glob, json, os, pathlib, re, subprocess, sys, textwrap, time, urllib.request
from . import gem

# ---- what things cost, from ai.google.dev/gemini-api/docs/pricing ------------
STILL_MODEL = "gemini-3.1-flash-lite-image"
STILL_PRICE = 0.0336
CLIP = {
    "lite":     ("veo-3.1-lite-generate-preview",  {"720p": 0.05, "1080p": 0.08}),
    "fast":     ("veo-3.1-fast-generate-preview",  {"720p": 0.10, "1080p": 0.12}),
    "standard": ("veo-3.1-generate-preview",       {"720p": 0.40, "1080p": 0.40}),
}
OMNI_MODEL, OMNI_PRICE_PER_S = "gemini-omni-1.1-flash", 0.154   # at 1080p
MUSIC_MODEL, MUSIC_PRICE = "lyria-3.5", 0.08
ASR_MODEL = "gemini-3.5-transcribe"
ALLOWED_SECONDS = {"720p": (4, 6, 8), "1080p": (8,), "4k": (8,)}


def run(args, what=""):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"\nffmpeg failed{(' during ' + what) if what else ''}:\n"
                 f"{p.stderr[-1500:]}")


def probe(path, entries="format=duration"):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries,
                           "-of", "csv=p=0", path],
                          capture_output=True, text=True).stdout.strip()


def need_ffmpeg():
    from shutil import which
    if not which("ffmpeg") or not which("ffprobe"):
        sys.exit("ffmpeg is not installed. See README.md, 'Before you start'.")


# --------------------------------------------------------------- stills ------
def make_still(beat, prompt, style, outdir="frames", force=False):
    """Draw one picture. Skips work already done, so a re-run after a crash or a
    daily limit costs nothing for the pictures it already has."""
    dst_existing = f"{outdir}/{beat}.png"
    if not force and os.path.exists(dst_existing) and os.path.getsize(dst_existing) > 0:
        return dst_existing
    from google.genai import types
    c = gem.client()
    cfg = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="9:16", image_size="1K"),
        http_options=types.HttpOptions(timeout=180_000))
    resp = c.models.generate_content(
        model=STILL_MODEL, contents=[f"{style}\n\n{prompt}"], config=cfg)
    dst = f"{outdir}/{beat}.png"
    if not gem.save_first_image(resp, dst):
        return None
    gem.log_spend("still", beat, STILL_PRICE, dst)
    return dst


def contact_sheet(beats, outdir="frames", dst="contact_sheet.png", cols=4):
    """One picture of all the shots, with the beat name burned on each."""
    paths = [f"{outdir}/{b}.png" for b in beats if os.path.exists(f"{outdir}/{b}.png")]
    if not paths:
        return None
    # tile() works across FRAMES of one stream, not across several inputs, so the
    # labelled stills are written as a numbered sequence and read back as one.
    os.makedirs("work/sheet", exist_ok=True)
    for f in glob.glob("work/sheet/*.png"):
        os.remove(f)
    present = [b for b in beats if os.path.exists(f"{outdir}/{b}.png")]
    for i, b in enumerate(present):
        run(["ffmpeg", "-v", "error", "-y", "-i", f"{outdir}/{b}.png", "-vf",
             f"scale=360:-1,pad=iw+8:ih+8:4:4:color=white,"
             f"drawtext=text='{b}':x=16:y=16:fontsize=34:fontcolor=white:"
             f"box=1:boxcolor=black@0.75:boxborderw=10",
             f"work/sheet/{i:03d}.png"], "labelling stills")
    rows = (len(present) + cols - 1) // cols
    run(["ffmpeg", "-v", "error", "-y", "-f", "image2", "-i", "work/sheet/%03d.png",
         "-vf", f"tile={cols}x{rows}:color=white", "-frames:v", "1", dst],
        "contact sheet")
    return dst


# ------------------------------------------------------------ narration ------
def transcribe(audio, out="words.json"):
    from google.genai import types
    c = gem.client()
    up = c.files.upload(file=audio)
    r = c.models.generate_content(
        model=ASR_MODEL, contents=[up],
        config=types.GenerateContentConfig(
            audio_transcription_config=types.AudioTranscriptionConfig(
                word_timestamp=True)))
    at = r.candidates[0].content.parts[0].audio_transcription
    d = at.model_dump()

    def secs(v):
        if v is None:
            return None
        s = str(v)
        return float(s[:-1]) if s.endswith("s") else float(s)

    words = [{"w": w["word"], "s": secs(w.get("start_offset")),
              "e": secs(w.get("end_offset"))} for w in (d.get("words") or [])]
    if not words:
        sys.exit("The transcription came back with no word timings. Try again; if "
                 "it keeps happening the recording may be too quiet or too noisy.")
    json.dump({"audio": audio, "text": d.get("text", ""), "words": words},
              open(out, "w"), indent=1)
    u = r.usage_metadata
    gem.log_spend("transcribe", f"{len(words)} words",
                  (getattr(u, "prompt_token_count", 0) or 0) * 2e-6)
    return words


def _norm(w):
    return w.lower().strip(".,!?;:—-“”\"'")


def find_retakes(words, min_words=5):
    ws = [_norm(w["w"]) for w in words]
    n, cuts, i = len(ws), [], 0
    while i < n:
        best = None
        for L in range(min(40, (n - i) // 2), min_words - 1, -1):
            a = ws[i:i + L]
            for j in range(i + L, min(i + L + 12, n - L + 1)):
                if ws[j:j + L] == a:
                    best = (L, j)
                    break
            if best:
                break
        if best:
            L, j = best
            cuts.append({"start": words[i]["s"], "end": words[j]["s"], "len": L,
                         "text": " ".join(w["w"] for w in words[i:i + L])})
            i = j + L
        else:
            i += 1
    return cuts


def cut_audio(src, cuts, dst):
    keep, pos = [], 0.0
    for c in cuts:
        if c["start"] > pos:
            keep.append((pos, c["start"]))
        pos = c["end"]
    keep.append((pos, None))
    parts = []
    for k, (s, e) in enumerate(keep):
        f = f"work/_seg{k}.m4a"
        args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}"]
        if e is not None:
            args += ["-to", f"{e:.3f}"]
        args += ["-i", src, "-c", "copy", f]
        run(args, "trimming retakes")
        parts.append(f)
    with open("work/_seglist.txt", "w") as fh:
        for p in parts:
            fh.write(f"file '{os.path.basename(p)}'\n")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", "work/_seglist.txt", "-c", "copy", dst], "joining audio")
    return dst


def align(words, shots):
    """Match beats to the words actually spoken. Raises if it cannot."""
    import difflib
    TOKEN = re.compile(r"[a-z0-9']+")

    def toks(s):
        return TOKEN.findall(s.lower().replace("—", " ").replace("-", " "))

    script, owner = [], []
    for i, sh in enumerate(shots):
        for t in toks(sh["text"]):
            script.append(t); owner.append(i)
    heard, hw = [], []
    for w in words:
        for t in toks(w["w"]):
            heard.append(t); hw.append(w)

    sm = difflib.SequenceMatcher(a=script, b=heard, autojunk=False)
    spans = {i: [] for i in range(len(shots))}
    for i1, j1, n in sm.get_matching_blocks():
        for k in range(n):
            spans[owner[i1 + k]].append(j1 + k)

    empty = [shots[i]["beat"] for i, v in spans.items() if not v]
    if empty:
        raise ValueError(
            f"Could not find beats {empty} anywhere in the recording.\n"
            "Usually this means a line was skipped, or read very differently "
            "from the script. Check narration_script.txt and re-record if needed.")
    firsts = [min(spans[i]) for i in range(len(shots))]
    lasts = [max(spans[i]) for i in range(len(shots))]
    if any(firsts[i] > firsts[i + 1] for i in range(len(shots) - 1)):
        raise ValueError("The beats came out of order against the recording. "
                         "Was the script read in a different order?")

    edges = [max(0.0, hw[firsts[0]]["s"] - 0.25)]
    for i in range(len(shots) - 1):
        a, b = hw[lasts[i]]["e"], hw[firsts[i + 1]]["s"]
        edges.append((a + b) / 2 if b > a else b)
    edges.append(hw[-1]["e"] + 0.25)
    for i, sh in enumerate(shots):
        sh["audio_start"] = round(edges[i], 3)
        sh["dur"] = round(edges[i + 1] - edges[i], 3)
    return shots


def split_long(words, shots, maxdur=8.0):
    """Split any beat over the clip ceiling at a real gap between words."""
    TOKEN = re.compile(r"[a-z0-9']+")
    hw = []
    for w in words:
        for _ in TOKEN.findall(w["w"].lower()):
            hw.append(w)
    out, made = [], []
    for sh in shots:
        if sh.get("dur", 0) <= maxdur:
            out.append(sh); continue
        st, en = sh["audio_start"], sh["audio_start"] + sh["dur"]
        idx = [i for i, w in enumerate(hw) if w["s"] >= st - .01 and w["e"] <= en + .01]
        mid, best, bs = (st + en) / 2, None, -1e9
        for k in range(1, len(idx)):
            prev, nxt = hw[idx[k - 1]], hw[idx[k]]
            t = (prev["e"] + nxt["s"]) / 2
            if t - st > maxdur or en - t > maxdur: continue
            if t - st < 1.2 or en - t < 1.2: continue
            score = (nxt["s"] - prev["e"]) * 3 - abs(t - mid) * .5
            if score > bs:
                best, bs = (k, t), score
        if not best:
            out.append(sh); continue
        k, t = best
        for suf, a, b, txt in (("i", st, t, " ".join(hw[i]["w"] for i in idx[:k])),
                               ("ii", t, en, " ".join(hw[i]["w"] for i in idx[k:]))):
            new = dict(sh)
            new.update(beat=f"{sh['beat']}-{suf}", audio_start=round(a, 3),
                       dur=round(b - a, 3), text=txt, split_from=sh["beat"])
            out.append(new); made.append(new["beat"])
    return out, made


# ---------------------------------------------------------------- clips ------
def purchased(dur, resolution):
    for s in ALLOWED_SECONDS[resolution]:
        if dur <= s:
            return s
    return None


def make_clip_veo(beat, prompt, style, dur, model, resolution, first_frame, outdir):
    from google.genai import types
    model_id, prices = CLIP[model]
    buy = purchased(dur, resolution)
    c = gem.client()
    kwargs = {}
    if first_frame and os.path.exists(first_frame):
        kwargs["image"] = types.Image.from_file(location=first_frame)
    op = c.models.generate_videos(
        model=model_id, prompt=f"{style}\n\n{prompt}",
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16", resolution=resolution,
            duration_seconds=buy, number_of_videos=1),
        **kwargs)
    while not op.done:
        time.sleep(10)
        op = c.operations.get(op)
    vids = getattr(op.response, "generated_videos", None) if op.response else None
    if not vids:
        return None, 0.0
    dst = f"{outdir}/beat_{beat}.mp4"
    os.makedirs(outdir, exist_ok=True)
    c.files.download(file=vids[0].video, destination=dst)
    cost = buy * prices[resolution]
    gem.log_spend(f"clip/{model}", beat, cost, dst)
    return dst, cost


def make_clip_omni(beat, prompt, style, resolution, first_frame, outdir):
    c = gem.client()
    payload = []
    if first_frame and os.path.exists(first_frame):
        payload.append({"type": "image", "mime_type": "image/png",
                        "data": base64.b64encode(
                            pathlib.Path(first_frame).read_bytes()).decode()})
    payload.append({"type": "text", "text": f"{style}\n\n{prompt}"})
    inter = c.interactions.create(
        model=OMNI_MODEL, input=payload,
        response_format={"type": "video", "aspect_ratio": "9:16",
                         "resolution": resolution, "delivery": "uri"})
    dst = f"{outdir}/beat_{beat}.mp4"
    os.makedirs(outdir, exist_ok=True)
    vid = getattr(inter, "output_video", None)
    raw = None
    if vid is not None:
        if getattr(vid, "data", None):
            raw = (vid.data if isinstance(vid.data, (bytes, bytearray))
                   else base64.b64decode(vid.data))
        elif getattr(vid, "uri", None):
            req = urllib.request.Request(
                vid.uri, headers={"x-goog-api-key": gem.api_key()})
            with urllib.request.urlopen(req) as r:
                raw = r.read()
    if not raw:
        return None, 0.0
    pathlib.Path(dst).write_bytes(raw)
    u = getattr(inter, "usage", None)
    tok = 0
    for a in ("output_tokens", "total_output_tokens", "candidates_token_count"):
        tok = getattr(u, a, None) if u else None
        if tok:
            break
    cost = (tok * 17.5e-6) if tok else 10 * OMNI_PRICE_PER_S
    gem.log_spend("clip/omni", beat, cost, dst)
    return dst, cost


# ---------------------------------------------------------------- music ------
def make_music(seconds, mood, instruments, dst="audio/music_bed.mp3"):
    c = gem.client()
    prompt = (f"Instrumental underscore for a {seconds}-second explainer film. "
              f"{instruments}. Mood: {mood}. Gentle forward motion, no build to a "
              f"climax, no drum fills, no vocals, no speech. Sparse enough to sit "
              f"underneath a spoken voice without competing with it. Ends softly.")
    r = c.models.generate_content(model=MUSIC_MODEL, contents=[prompt])
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    for part in r.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            raw = (inline.data if isinstance(inline.data, (bytes, bytearray))
                   else base64.b64decode(inline.data))
            pathlib.Path(dst).write_bytes(raw)
            gem.log_spend("music", "1 track", MUSIC_PRICE, dst)
            return dst
    return None
