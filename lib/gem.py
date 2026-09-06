#!/usr/bin/env python3
"""
Shared plumbing: the API key, the model calls, and the spend log.

Everything in this pipeline goes through here, so there is one place that knows
how to find the key, one place that decides which model does what, and one place
that records what was spent.
"""
import base64, json, logging, os, pathlib, re, sys, time, warnings

warnings.filterwarnings("ignore")
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)

HERE = pathlib.Path(__file__).resolve().parent.parent   # the halmos folder
SPEND = pathlib.Path("spend.log")                        # written where you run

# The key lives outside this folder, in your own home directory, so that copying,
# zipping, sharing or publishing the folder can never carry the key with it.
KEY_FILE = pathlib.Path.home() / ".config" / "halmos" / "key"


def key_instructions():
    """The exact thing to type, for someone who has not done this before."""
    return (
        f"  Mac or Linux - paste these two lines into a Terminal window,\n"
        f"  putting your own key where it says YOUR-KEY-HERE:\n\n"
        f"      mkdir -p ~/.config/halmos\n"
        f"      printf %s 'YOUR-KEY-HERE' > ~/.config/halmos/key && "
        f"chmod 600 ~/.config/halmos/key\n\n"
        f"  Windows - create the file {KEY_FILE} yourself and put the key on the\n"
        f"  first line, or set an environment variable called GEMINI_API_KEY.\n\n"
        f"  Get a key at aistudio.google.com. It needs billing switched on -\n"
        f"  see README.md.\n")


# ---------------------------------------------------------------- the key ----
def api_key():
    """The Gemini API key, from the environment or from your home directory.

    Looked for in two places, in this order:

      1. the GEMINI_API_KEY environment variable
      2. ~/.config/halmos/key

    Deliberately NOT anywhere inside this folder. The key is never printed, never
    written into any output, and never committed - the folder has no copy of it
    to commit. Anything found is stripped of whitespace and read from line one.
    """
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    if KEY_FILE.exists():
        lines = [ln.strip() for ln in KEY_FILE.read_text().splitlines()]
        for line in lines:
            if line and not line.startswith("#"):
                if line.startswith("PASTE") or line == "YOUR-KEY-HERE":
                    break
                return line
        sys.exit(f"{KEY_FILE} exists but has no key in it.\n\n"
                 + key_instructions())
    sys.exit("No API key found.\n\n" + key_instructions())


def need_package():
    """Check once, up front, with a message a person can act on. Without this the
    first thing a new user sees is a Python traceback."""
    try:
        import google.genai  # noqa: F401
    except ImportError:
        sys.exit("\nThe google-genai package is not installed.\n\n"
                 "  Run this, then try again:\n"
                 "      pip install google-genai\n\n"
                 "  (If 'pip' is not found, try 'pip3' or 'python3 -m pip'.)\n")


def client():
    need_package()
    from google import genai
    return genai.Client(api_key=api_key())


# --------------------------------------------------------------- settings ----
def settings():
    f = HERE / "settings.json"
    s = json.loads(f.read_text()) if f.exists() else {}
    s.setdefault("resolution", "1080p")
    s.setdefault("target_lufs", -14)
    s.setdefault("music_mood", "warm and unhurried")
    s.setdefault("music_instruments", "soft piano and light strings")
    s.setdefault("video_name", "myvideo")
    s.setdefault("caption_font_file", "")
    s.setdefault("caption_font_family", "")
    s.setdefault("clip_models", ["lite", "fast", "omni"])
    s.setdefault("max_spend_usd", 20.0)
    s.setdefault("words_per_minute", 130)
    return s


def style_block():
    """The look of every shot, as the user wrote it. Comment lines are dropped."""
    f = HERE / "style_block.txt"
    if not f.exists():
        sys.exit(f"Missing {f}. It holds the look of every shot - see STYLE.md.")
    body = [ln for ln in f.read_text().splitlines() if not ln.strip().startswith("#")]
    text = " ".join(" ".join(body).split())
    if text.startswith("Describe your look here"):
        sys.exit("style_block.txt still has the placeholder text in it.\n"
                 "Open it, describe the look you want, save, and run again.\n"
                 "STYLE.md explains what to write.")
    if len(text) < 60:
        sys.exit("style_block.txt looks empty. Describe the look you want in it.")
    return text


# ------------------------------------------------------------------ spend ----
def log_spend(kind, detail, usd, note=""):
    SPEND.open("a").write(
        f"{time.strftime('%F %T')}\t{kind}\t{detail}\t${usd:.4f}\t{note}\n")


def spent_so_far():
    if not SPEND.exists():
        return 0.0
    tot = 0.0
    for line in SPEND.read_text().splitlines():
        for part in line.split("\t"):
            if part.startswith("$"):
                try:
                    tot += float(part[1:])
                except ValueError:
                    pass
    return tot


def check_budget(about_to_spend, s=None):
    """Refuse to start something that would blow the ceiling in settings.json."""
    s = s or settings()
    cap = s["max_spend_usd"]
    now = spent_so_far()
    if now + about_to_spend > cap:
        sys.exit(f"\nSTOPPING. This would spend ${now + about_to_spend:.2f} in total, "
                 f"over the ${cap:.2f} ceiling in settings.json.\n"
                 f"Already spent: ${now:.2f}. Raise the ceiling there if you meant to.")


# ------------------------------------------------------------- text model ----
TEXT_MODEL = "gemini-3.5-flash"


def ask(prompt, images=None, want_json=True, retries=3):  # noqa: C901
    """One question to the text/vision model. Returns parsed JSON, or the text.

    This is where the pipeline's judgement lives: splitting a script into beats,
    writing a shot prompt, deciding whether a picture matches its sentence.
    """
    c = client()
    from google.genai import types
    contents = []
    for img in (images or []):
        contents.append(types.Part.from_bytes(
            data=pathlib.Path(img).read_bytes(), mime_type="image/png"))
    contents.append(prompt)

    last = None
    for attempt in range(retries):
        try:
            from google.genai import types as _t
            r = c.models.generate_content(
                model=TEXT_MODEL, contents=contents,
                config=_t.GenerateContentConfig(
                    http_options=_t.HttpOptions(timeout=120_000)))
            txt = (r.text or "").strip()
            u = r.usage_metadata
            ti = getattr(u, "prompt_token_count", 0) or 0
            to = getattr(u, "candidates_token_count", 0) or 0
            # gemini-3.5-flash: $1.50/1M in, $9.00/1M out
            log_spend("think", f"{ti}+{to} tok", ti * 1.5e-6 + to * 9.0e-6)
            if not want_json:
                return txt
            m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S)
            if m:
                txt = m.group(1).strip()
            start = min([i for i in (txt.find("{"), txt.find("[")) if i >= 0] or [0])
            return json.loads(txt[start:])
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"model call failed after {retries} tries: {last}")


# ------------------------------------------------------------ small utils ----
def say(msg):
    """Progress. The generation steps take half an hour and look like nothing is
    happening; silence is what makes people think it has broken."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save_first_image(resp, path):
    for cand in (resp.candidates or []):
        for part in (cand.content.parts or []):
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                raw = (inline.data if isinstance(inline.data, (bytes, bytearray))
                       else base64.b64decode(inline.data))
                pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(path).write_bytes(raw)
                return True
    return False
