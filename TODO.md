# Known gaps

Things halmos should do and does not yet. Written down so that nobody has to
rediscover them, and so that anyone looking for somewhere to start has one.

Nothing here is a bug you will hit on a normal run. They are the difference
between something that works and something that can be relied on.

---

## 1. Tests and lint checks — mostly done

**There is now a real test suite** (`tests/`, 117 tests) and `ruff`
check/format both run clean. What's left:

- **CI is still not set up.** Everything except the Tier 3 model-call tests
  runs with no API key and no network, so it can run on every push — that
  just hasn't been wired up as a GitHub Actions workflow yet. GitHub's Ubuntu
  runners' `apt` ffmpeg typically includes `libass`/`drawtext` by default
  (unlike Homebrew's slimmed `ffmpeg` formula, which needs `ffmpeg-full` —
  see the "Before you start" section of `README.md`), so a plain
  `apt-get install ffmpeg` should work in CI without needing anything
  special, but this hasn't been verified on an actual runner.
- The original four historical bugs, the three test tiers, and the lint pass
  are all done — see `SPEC.md`/`CLAUDE.md`/`DIARY.md` in the parent
  `halmos-code/` folder (not part of this repo) for the full account of how
  the suite was built, including two real bugs found while writing it
  (`edit._ass_time()`'s invalid-timestamp bug, and `make_still()` writing
  JPEG bytes into `.png`-named files) and one found in the installation
  instructions themselves (`brew install ffmpeg` lacks the caption-rendering
  library — see `README.md`).

## 2. Handle errors from Gemini, and everything else, gracefully — partially done

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
- **Say what it was doing** — done for clip generation specifically (the
  scenario this item's own description uses as the example): the beat, how
  many clips are already made, and money spent so far.

What's still not done:

- **A persistent note about partial progress.** The improved exit messages
  cover the immediate "what do I do now" need, but there's no separate
  status file surviving between runs beyond what's already inferable from
  which files exist in `gen/`. Whether that's worth adding on top of the
  clearer messages is an open question, not a settled no.
- **The non-Gemini failures.** A missing `ffmpeg` is already handled
  (`media.need_ffmpeg()`); a bad recording format or a missing font file
  mostly surface through `ffmpeg`'s own stderr via `lib/media.py`'s `run()`,
  which is usually clear enough on its own but was never deliberately
  improved. A full disk isn't handled specially anywhere — it would surface
  as a raw `OSError`, which is at least self-explanatory ("No space left on
  device") even unhandled.
- **"Say what it was doing" beyond clip generation** — `choose_inpoint()`,
  `check_frames()`, and the still-generation/review loop in `1_plan.py`
  already degrade gracefully (best-effort fallbacks, not crashes) but don't
  yet report beat/spend context the way the clip loop now does.

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
