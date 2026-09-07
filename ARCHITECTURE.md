# How halmos actually works

`README.md` describes halmos from the outside: two commands, in between you
look at pictures and record yourself. This document describes the machinery
underneath — for the next person (or the next session) who has to change it.
Not a rewrite of the README; a map of `lib/` for someone about to edit it.

## The shape of a run

```
1_plan.py                          2_make.py
  script.txt ──┐                     plan.json ──┐
  style_block.txt                    corrections.txt
       │                             audio/narration.*
       ▼                                  │
  plan.split_into_beats()                 ▼
  plan.write_prompts()               plan.apply_corrections()  (if any)
       │                             media.transcribe()
       ▼                             media.find_retakes() → media.cut_audio()
  media.make_still() × N beats       media.align()
  plan.review_still() × N            media.split_long()
       │                                  │
       ▼                                  ▼
  media.contact_sheet()              media.make_clip_veo() / make_clip_omni()
       │                             media.make_music()
       ▼                                  │
  plan.json, narration_script.txt,        ▼
  corrections.txt                    edit.choose_inpoint() × N shots
                                      edit.build()
                                      edit.loudness(), edit.check_frames()
                                           │
                                           ▼
                                      out/<name>.mp4
```

`plan.json` is the handoff between the two commands. Its shape:

```json
{
  "video": "myvideo", "width": 1080, "height": 1920, "fps": 30,
  "words_per_minute": 130,
  "beats": [{"beat": "1", "text": "...", "prompt": "..."}, ...]
}
```

## `lib/gem.py` — shared plumbing

Everything that touches the API key, calls a model, or tracks spend goes
through here. Nothing here knows about beats, shots, or video — it is the
one place that knows *how* to ask, not *what* to ask.

- **The key.** `api_key()` checks `GEMINI_API_KEY` then `~/.config/halmos/key`,
  deliberately never inside the project folder. `client()` builds the SDK
  client from it.
- **The project folder.** `gem.PROJECT_DIR` (default: the current directory)
  is where `settings.json`/`style_block.txt` are looked for and everything
  gets written. `1_plan.py`/`2_make.py` reassign it from `--out`/`--project`
  before doing anything else; nothing downstream needs to know whether a
  project flag was given.
- **Settings.** `settings()` reads `PROJECT_DIR/settings.json`, falling back
  to `~/.config/halmos/settings.json`, falling back to built-in defaults —
  so a house style and spending limit can be set once rather than per video.
  `style_block()` defaults to `PROJECT_DIR/style_block.txt` but accepts an
  explicit `path=` to use a style file shared across several projects
  (`--style` resolves to this); it strips `#` comment lines and rejects the
  placeholder text or anything under 60 characters.
- **Spend.** `log_spend(kind, detail, usd, note)` appends one tab-separated
  line to `spend_path()` (`PROJECT_DIR/spend.log`). `spent_so_far()` sums
  every `$`-prefixed field across all lines, tolerating malformed ones.
  `check_budget()` compares a prospective spend against
  `settings()["max_spend_usd"]` and exits before spending if it would cross
  the ceiling.
- **`ask(prompt, images=None, want_json=True, retries=3)`** is the one text/
  vision call in the whole pipeline. It sends `prompt` (plus any images as
  inline bytes) to `TEXT_MODEL`, strips a ` ```json ` fence if present, finds
  the first `{` or `[` in the response and parses from there (tolerating
  leading prose before the JSON starts), and retries with a fixed 2/5/8-second
  backoff on any exception before raising `RuntimeError`. Every judgement call
  in the pipeline — splitting beats, writing prompts, reviewing a still, an
  in-point choice — is one call to this function with a different prompt.

## `lib/plan.py` — the judgement half

Turns a script into beats, and beats into image prompts. Two Gemini text
calls plus one vision call that grades its own output.

- **`split_into_beats(script_text, wpm)`** — one `gem.ask()` call with
  `BEAT_RULES`, asking for `{"beats": [{"beat": "1", "text": "..."}]}`. The
  one hard guarantee: every word of the script must survive, unreordered —
  enforced by comparing `[a-z0-9']+` tokens of the joined beat text against
  the same tokenisation of the original script, raising `ValueError` on any
  mismatch. Warns (doesn't fail) if a beat looks likely to run over 8 seconds
  once split by `words_per_minute`.
- **`write_prompts(beats, style)`** — one `gem.ask()` call with `PROMPT_RULES`
  and the style block, returning `{beat: prompt}` for every beat. Raises if
  any beat comes back without a prompt.
- **`review_still(image_path, beat_text, prompt, style)`** — one vision call
  per still: does the picture carry every claim in the sentence, is there any
  text in it, is it a single image (not a grid), are there photographic
  hands, does it match the style. Returns `{"ok": bool, "problems": [...],
  "revised_prompt": "..."}` — the caller (`1_plan.py`) redraws with
  `revised_prompt` when `ok` is false.
- **`apply_corrections(items, style)`** — one `gem.ask()` call per *run* of
  `2_make.py` (not per correction), rewriting prompts for beats the human
  flagged wrong in `corrections.txt`. `items` is `[{beat, text, prompt,
  note}]`; returns `{beat: new_prompt}`.

## `lib/media.py` — the mechanical half, plus the model calls that generate media

Two different kinds of function live here, deliberately not split into
separate files (yet): pure/deterministic helpers, and thin wrappers around a
Gemini call that generates a still, a clip, or music.

**Model-calling:**
- `make_still(beat, prompt, style, outdir, force=False)` — one image call,
  skips work already on disk unless `force=True`. As of 2026-09-06 the model
  returns JPEG bytes even though the destination is named `.png`; see
  `gem.save_first_image()`, which re-encodes via ffmpeg when the real
  `mime_type` doesn't match the `.png` extension.
- `make_clip_veo(...)` / `make_clip_omni(...)` — one video-generation call
  each, on two different model families (`CLIP` dict vs `OMNI_MODEL`).
  `2_make.py` tries each model in `settings()["clip_models"]` order per shot,
  falling through to the next on failure.
- `make_music(seconds, mood, instruments, dst)` — one music-generation call
  for the whole video's underscore.
- `transcribe(audio, out)` — one ASR call, returning word-level timestamps.
  Exits if the model returns no words at all (usually a bad recording).

**Pure/deterministic** (see `tests/test_media_pure.py` for the exhaustive
edge-case list):
- `find_retakes(words, min_words=5)` — detects a spoken false-start-then-retry
  by finding a repeated run of ≥5 words within a 12-word lookahead window,
  greedily preferring the longest match. Returns cut spans to remove.
- `align(words, shots)` — matches each shot's script text against the actual
  spoken words via `difflib.SequenceMatcher`, and derives `audio_start`/`dur`
  for every shot from where its words were found, splitting the difference at
  each boundary. Raises if a beat has no matches at all, or (in principle;
  see the test suite's note on why this may be unreachable via real input) if
  beats come back out of order.
- `split_long(words, shots, maxdur)` — splits any shot whose derived duration
  exceeds `maxdur`, at the widest real word-gap near the middle, provided
  the resulting halves both fit and neither is under 1.2 seconds. Silently
  leaves an over-length shot unsplit if no such gap exists (a known gap; see
  TODO.md item 2).
- `next_longest_available_clip(dur, resolution)` — Google's video models
  sell clips only in fixed lengths (`ALLOWED_SECONDS`); this returns the
  smallest one that's at least `dur` seconds, or `None` if even the longest
  is too short.
- `contact_sheet(beats, outdir, dst, cols)` — labels each still with its beat
  name via ffmpeg's `drawtext`, then tiles them via `image2`-sequence input
  (not multiple `-i` flags — `tile` only tiles frames of one stream over
  time; see the regression test for the historical bug this avoids).

## `lib/edit.py` — the deterministic edit

One judgement call (`choose_inpoint`, which window of a generated clip to
keep); everything else is ffmpeg with no model in the loop.

- `choose_inpoint(clip_path, beat_text, dur, work)` — samples 6 evenly-spaced
  frames from the clip into one strip image, asks the vision model which
  in-point reads best for the sentence and whether the action runs backwards.
  `_parse_fps()` (extracted 2026-09-06, previously inline) parses `ffprobe`'s
  per-stream frame-rate output, defaulting to 24fps for anything that isn't a
  clean positive ratio — the audio stream's own rate reports `0/0`.
- `_chunks(text, per=6)` — groups a shot's words into ~6-word caption chunks,
  extending a chunk past the boundary if the word that would end it is a
  function word (`FUNCTION_WORDS`), and folding a trailing group under 3
  words into the previous chunk rather than giving it its own caption.
- `_ass_time(t)` — formats a float number of seconds as an ASS `h:mm:ss.cc`
  timestamp, by rounding to whole centiseconds first and decomposing that
  integer (rounding a live seconds field can otherwise produce an invalid
  `60.00` — fixed 2026-09-06).
- `build(cfg, work, out)` — the whole edit: cuts each shot from its source
  clip to its exact duration (with an optional reverse-playback path),
  writes an `.ass` caption file from `_chunks`/`_ass_time`, concatenates the
  cut shots, and muxes in narration (loudness-normalised, trimmed to the
  video's total duration) plus an optional side-chain-ducked music bed, or
  silence if there's no narration yet. Returns `(final_path, total_seconds)`.
- `loudness(path)` — runs ffmpeg's `ebur128` filter and parses the integrated
  loudness (`I: ... LUFS`) from stderr.
- `check_frames(video, shots, work)` — samples one frame per shot at 60% of
  its duration, tiles them, and asks the vision model to flag stray text,
  hands, or broken frames — best-effort; swallows exceptions and returns no
  problems rather than failing the whole run over a QA check.

**`cfg`'s shape**, the argument to `build()` — this is the thing a newcomer
to `lib/edit.py` currently has to reconstruct from usage:

```python
{
    "video": str,
    "width": int,
    "height": int,
    "fps": int,
    "shots": [
        {
            "beat": str,
            "text": str,
            "dur": float,
            "src": str,
            "in": float,
            "reverse": bool,
        }  # in/reverse from choose_inpoint()
    ],
    "sources": {"<src>": {"file": "path/to/clip.mp4"}},
    "narration": {"file": "path/to/audio", "start": float} | absent,
    "music": {"file": "path/to/audio.mp3", "gain_db": float} | absent,
    "target_lufs": float,
    "caption_font_family": str,
    "caption_font_file": str,
}
```

## `1_plan.py` / `2_make.py` — the two commands

(`0_check.py` is a third, smaller script alongside them — a preflight
environment check with no `PROJECT_DIR`, no argument parsing, and no side
effects: it calls `media.ffmpeg_diagnostic()` (does ffmpeg actually *run* -
`which` finding a binary is not proof of that; see below),
`media.has_ffmpeg_filter()`, `gem.api_key()`, and the package-import check
already used elsewhere, and reports every problem it finds rather than
exiting on the first one. It exists so the failure modes below - a missing
library, a broken install, a missing key - are caught before a real run
rather than partway through one.)

`1_plan.py`/`2_make.py` are both linear scripts, not modules meant to be imported — `main(argv=None)`
in each parses arguments (via `parse_args(argv)`, so tests can call `main()`
directly without touching `sys.argv`), reads inputs, calls into `lib/`, and
writes outputs, in the order shown in the diagram above. `main()` is the
first thing that touches `gem.PROJECT_DIR` — it resolves `--out`/`--project`
(default: the current directory) and assigns it before calling anything else,
so every function downstream just uses `PROJECT_DIR` or an explicit path
argument and never needs to know whether a project flag was given.

`1_plan.py --script`/`--style` default to filenames inside `--out` (so a
plain `python3 1_plan.py` behaves exactly as before); given explicitly, they
can point anywhere — the mechanism for a style file shared across several
projects. `1_plan.py` records the *resolved* style path into `plan.json` as
`"style_source"`, so `2_make.py` picks up the same style automatically
without repeating `--style` (it also accepts its own `--style`, which takes
priority over the recorded one).

Read the two scripts top to bottom; there is no indirection to trace through
beyond the `lib/` calls documented above.

## Known structural gaps, for context

- **Clip generation and the edit have no CLI tests.** `tests/test_cli.py`'s
  end-to-end test runs `1_plan.py` fully and `2_make.py` as far as recording
  alignment against a real project folder, but stops before clip generation
  — faking Veo's async operation-polling protocol (and the omni model's
  separate `interactions` API) is a bigger undertaking than this pass
  covered. `edit.build()`'s own path-parameter plumbing is exercised
  directly by `tests/test_ffmpeg_chain.py` instead, just not from inside a
  full `2_make.py` run.
- **Not installable yet.** TODO.md item 3's "ideally `pip install halmos`"
  is unaddressed — the two scripts are still run with `python3 1_plan.py`
  from wherever the checkout lives, just no longer *from inside* it.
