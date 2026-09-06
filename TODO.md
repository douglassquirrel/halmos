# Known gaps

Things halmos should do and does not yet. Written down so that nobody has to
rediscover them, and so that anyone looking for somewhere to start has one.

Nothing here is a bug you will hit on a normal run. They are the difference
between something that works and something that can be relied on.

---

## 1. Tests and lint checks — done

**There is now a real test suite** (`tests/`, 117 tests) and `ruff`
check/format both run clean.

- **CI is now wired up** (`.github/workflows/tests.yml`): every push and PR
  runs the full suite plus lint on `ubuntu-latest`, no secrets configured
  because nothing in the suite needs a key or network — every tier
  (including Tier 3, the recorded-response replay) runs against a
  monkeypatched `gem.client()`, never a real one. (Earlier wording here said
  only Tier 3 was network/key-free, which was stale — all three tiers are;
  Tier 2 just additionally needs the `ffmpeg` binary present, and Tier 3
  needs `google-genai` importable, both already handled by the
  `requires_ffmpeg`/`requires_libass`/`requires_drawtext`/
  `requires_google_genai` skip-guards in `tests/conftest.py`.) GitHub's
  Ubuntu runners' `apt` ffmpeg typically includes `libass`/`drawtext` by
  default (unlike Homebrew's slimmed `ffmpeg` formula, which needs
  `ffmpeg-full` — see the "Before you start" section of `README.md`), so a
  plain `apt-get install ffmpeg` was used rather than anything special —
  confirmed on the first real run (green, 57s): the assumption holds. If a
  future runner image ever lacks them, the skip-guards mean Tier 2 skips
  cleanly rather than failing.
- The original four historical bugs, the three test tiers, and the lint pass
  are all done — see `SPEC.md`/`CLAUDE.md`/`DIARY.md` in the parent
  `halmos-code/` folder (not part of this repo) for the full account of how
  the suite was built, including two real bugs found while writing it
  (`edit._ass_time()`'s invalid-timestamp bug, and `make_still()` writing
  JPEG bytes into `.png`-named files) and one found in the installation
  instructions themselves (`brew install ffmpeg` lacks the caption-rendering
  library — see `README.md`).

## 2. Handle errors from Gemini, and everything else, gracefully — mostly done

What's done, grounded in real error shapes captured against the live API
(`google.genai.errors.APIError` exposes structured `.code`/`.status`
attributes, not just a message string):

- **RESOURCE_EXHAUSTED's two sub-cases are distinguished** — the daily quota
  and a depleted prepayment balance now produce different, actionable
  messages the moment they happen (`gem.classify_error()`/`gem.explain_error()`
  in `lib/gem.py`), rather than looking the same.
- **Fail once, not eleven times.** An invalid key, an unbilled account, or a
  retired model name now stops the run immediately — in `gem.ask()`'s retry
  loop and in `2_make.py`'s clip-generation loop — instead of failing the
  same way for every remaining call. The clip loop also stops once every
  configured model in `clip_models` is confirmed to have exhausted today's
  quota, rather than working through the remaining shots the same way.
- **Retries are honest.** `gem.ask()` uses exponential backoff with jitter
  (`gem.backoff_delay()`) for the classes actually worth retrying (a bare
  rate limit, or a genuinely transient failure), not a fixed 2/5/8s sequence
  applied to everything including errors retrying can't fix.
- **Model deprecation** now says which constant in `lib/media.py` (or
  `lib/gem.py`) to change, instead of a bare 404.
- **Say what it was doing, everywhere a model gets called in a loop.**
  Originally done for clip generation only; now also covers the three gaps
  this item used to name explicitly:
  - `1_plan.py`'s still-drawing loop (`media.make_still()`, which calls
    `gem.client()` directly, not through `gem.ask()`) previously had no
    error handling at all — an exception mid-run crashed with a raw
    traceback. Now classifies via `gem.classify_error()` and stops with the
    beat, how many pictures are already drawn, and spend so far, the same
    shape as the clip loop's message.
  - `1_plan.py`'s review loop (`plan.review_still()`) previously caught
    every exception the same bare way and silently moved to the next beat -
    indistinguishable from "reviewed, nothing wrong" even when the cause was
    an invalid key that would fail identically for every remaining beat.
    Now stops with beat/progress/spend context on the specific classes
    retrying can't fix; a one-off glitch still degrades to "skip this beat's
    review" as before.
  - `2_make.py`'s `edit.choose_inpoint()` loop previously caught every
    exception the same way and fell back to a centred crop - correct for a
    one-off glitch, silently wrong for a whole video's worth of shots in a
    row if the actual cause was e.g. an exhausted quota. Now stops the same
    way as the clip loop; falls back to centring only for the errors that
    can't be classified as unrecoverable.
  - `edit.check_frames()`'s single call at the very end now lets the same
    unrecoverable classes propagate (reported by `2_make.py` as "could not
    check the finished frames," not silently treated as "checked, found
    nothing wrong") rather than swallowing everything indiscriminately.

  Enabled by a new `gem.FatalModelError(RuntimeError)`, raised by `gem.ask()`
  for the four unrecoverable classes so a caller looping over several items
  can catch it specifically, distinct from the plain `RuntimeError` raised
  when retries are simply exhausted (which stays a per-item, not
  whole-loop, signal). Functions that call `gem.client()` directly instead
  of going through `gem.ask()` (`media.make_still`, `media.make_clip_veo`/
  `make_clip_omni`) still classify the raw exception themselves via
  `gem.classify_error()`, as the clip loop already did.

What's still not done, **both decided against for now, 2026-09-06** (not
forgotten, deliberately skipped until either turns into a real problem):

- **A persistent note about partial progress.** The improved exit messages
  cover the immediate "what do I do now" need, and the pipeline's real state
  already lives in the filesystem (`make_still`/clip generation both skip
  work that already exists) — a separate status file would be a second
  source of truth that could drift from the first. Not building it.
- **The non-Gemini failures.** A missing `ffmpeg` is already handled
  (`media.need_ffmpeg()`); a bad recording format or a missing font file
  mostly surface through `ffmpeg`'s own stderr via `lib/media.py`'s `run()`.
  Unlike the Gemini error work, which had exactly four known, real, captured
  error shapes to key off of, `ffmpeg` failures are far more varied
  (codecs, corrupt files, permissions, disk space, missing fonts...) and
  guessing at translations for all of them risks getting more of them wrong
  than it helps. A full disk isn't handled specially anywhere either — it
  would surface as a raw `OSError`, self-explanatory ("No space left on
  device") even unhandled. Not worth building general `ffmpeg`-failure
  classification speculatively; revisit if a specific case actually bites
  someone.

## 3. Never make the user edit the folder — done

`1_plan.py`/`2_make.py` now take `--script`, `--style`, and `--out`/
`--project`:

```
python3 1_plan.py  --script ~/videos/bees/script.txt \
                   --style  ~/videos/house-style.txt \
                   --out    ~/videos/bees
python3 2_make.py  --project ~/videos/bees
```

With no flags, both commands behave exactly as before (the project folder
defaults to the current directory). `settings.json` and `style_block.txt`
resolve against the project folder, falling back to
`~/.config/halmos/settings.json` for settings; `1_plan.py` records the
resolved style path into `plan.json` as `"style_source"` so `2_make.py`
picks up the same shared style automatically. Everything written —
`frames/`, `gen/`, `work/`, `out/`, `plan.json`, `spend.log`,
`corrections.txt`, `audio/` — now lands under the project folder.

**Not done:** the "ideally `pip install halmos`" stretch goal. The two
scripts are still run with `python3 1_plan.py` from wherever the checkout
lives — just no longer *from inside* it. Turning this into an installable
package with `halmos plan`/`halmos make` entry points is a separate,
larger effort (packaging, an entry-point CLI wrapper, a PyPI listing) that
this pass didn't attempt.

## 4. A written description of how the pipeline actually works — done

See `ARCHITECTURE.md`: the beat/prompt pipeline, the model-calling and
pure-function split in `lib/media.py` (including `cfg`'s shape, which
`edit.build()`'s callers previously had to reconstruct from usage alone),
the edit/mux pipeline, and the settings/spend model — plus a couple of
structural gaps worth knowing about (no CLI test covers clip generation
through the finished edit; see `ARCHITECTURE.md`'s own "Known structural
gaps" section).
