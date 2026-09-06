# Known gaps

Things halmos should do and does not yet. Written down so that nobody has to
rediscover them, and so that anyone looking for somewhere to start has one.

Nothing here is a bug you will hit on a normal run. They are the difference
between something that works and something that can be relied on.

---

## 1. Tests and lint checks

**There are none.** Not one automated test, and no linter runs anywhere.

Every defect this project has had was found by running the whole pipeline end to
end and looking at what came out, which costs money and the better part of an
hour. Several of them would have been caught in a second by a test:

- `contact_sheet()` composited twelve stills into a picture of the first one.
  `ffmpeg`'s `tile` filter tiles frames of one stream over time, not several
  inputs. A test asserting that the sheet contains twelve distinct tiles would
  have caught it.
- The in-point chooser parsed frame rate from `ffprobe` output that has one line
  per stream. The audio stream reports `0/0`, so the parse threw, so **every**
  shot fell back to a centred crop — silently. A test with a real two-stream
  file would have caught it.
- The finished audio ran 3.2 seconds past the end of the video, because
  `-shortest` does not apply to a filter-graph output. A test comparing the two
  durations would have caught it.
- A caption style keyed off the beat being named `"1"`, and stopped applying the
  moment beat 1 got split in two.

What is wanted:

- **Unit tests** for everything that does not call a model: the beat splitter's
  word-for-word guarantee, `align()`, `find_retakes()`, `split_long()`, the
  comment stripping in `style_block()`, `spent_so_far()`, `check_budget()`.
  These are pure functions with awkward edge cases and they are where the
  arithmetic bugs live.
- **A fixture-based test for the ffmpeg chain.** Generate two seconds of tone
  and colour bars with ffmpeg itself, run the real `build()` over them, and
  assert on durations, stream count and measured loudness. No API key needed and
  it costs nothing, which is the point: it can run on every commit.
- **A recorded-response test for the model calls.** Save one real response from
  each of `ask()`, `make_still()`, `transcribe()` and replay it, so the JSON
  parsing and the retry logic are exercised without spending anything.
- **Lint.** `ruff` and `black` would do. There is dead code in here and at least
  one shadowed name; a linter finds those for free.
- **CI.** Everything above except the model calls runs without a key, so it can
  run on every push.

## 2. Handle errors from Gemini, and everything else, gracefully

Right now an API failure that is not a transient 429 usually surfaces as a
traceback, and a run that dies at clip nine of twelve tells you very little about
what it was doing or what it had already paid for.

Specifically:

- **Distinguish the failures that mean different things.** `RESOURCE_EXHAUSTED`
  is two completely different situations — the daily per-model quota, where the
  answer is "come back tomorrow and re-run, nothing is lost", and an empty
  prepayment balance, where the answer is "top up the account". They currently
  look the same. `TROUBLESHOOTING.md` explains the difference; the program
  should say it at the moment it happens.
- **Say what it was doing.** Every failure should name the step, the beat, and
  what has already been spent, because the next question is always "how much of
  that do I have to pay for again?"
- **Fail once, not eleven times.** An invalid key or an unbilled account fails
  identically for every clip. Detect the unrecoverable class and stop.
- **Retries should be honest.** `ask()` retries three times with a fixed backoff
  and then raises the last exception. Rate limits want exponential backoff with
  jitter, and the free-tier limit is two requests per minute — a retry storm is
  how you trip it while recovering from it.
- **Partial results should survive.** A crash in step 2 should leave the clips
  already made, and it does; but it should also leave a note saying what is
  missing, so re-running is obviously the right move rather than a gamble.
- **Model deprecation.** When Google retires a model name the error is a flat
  404 with no hint. It should say which constant in `lib/media.py` to change.
- **The non-Gemini failures too.** A missing `ffmpeg`, a full disk, a recording
  in a format that will not decode, a font file that does not exist.

## 3. Never make the user edit the folder

The biggest remaining awkwardness in the design. Today halmos expects to *be* the
working directory: your words go in `script.txt` inside it, your look goes in
`style_block.txt` inside it, and the outputs land in it. That means a copy of the
whole toolkit per video, editing files inside a checked-out git repository, and
`git status` showing your own writing as a local modification.

It should be possible to install halmos once and never touch it again:

```
python3 1_plan.py  --script ~/videos/bees/script.txt \
                   --style  ~/videos/house-style.txt \
                   --out    ~/videos/bees
python3 2_make.py  --project ~/videos/bees
```

That means:

- `--script`, `--style`, `--out` / `--project` as command-line arguments, with
  the current filenames as defaults so nothing breaks for anyone already using it.
- `settings.json` found in the project folder, falling back to a user-level
  default in `~/.config/halmos/settings.json`, so a house style and a spending
  limit are set once rather than per video.
- Everything written — `frames/`, `gen/`, `work/`, `out/`, `plan.json`,
  `spend.log`, `corrections.txt` — under the project folder, not the current
  directory. `SPEND` in `lib/gem.py` is a bare relative path today, so the spend
  log lands wherever you happened to be standing.
- A **shared style file** referenced by many projects, which is the whole point:
  the look is meant to be the thing that stays the same across videos.
- Ideally installable (`pip install halmos`, or just `pipx`), so `halmos plan`
  and `halmos make` work from anywhere and the repository is never the working
  directory at all.

The API key already works this way, and that is the model to follow: it lives in
`~/.config/halmos/key`, halmos finds it, and nobody edits anything to make that
happen.

## 4. A written description of how the pipeline actually works

Right now there are two documents: `README.md`, which describes halmos from
the outside as two commands to run, and this file, which describes what's
missing. Neither describes what `1_plan.py` and `2_make.py` actually do
underneath — the beat/prompt pipeline, what each still/clip/music call
expects and returns, the edit/mux pipeline, the settings and spend model.

That gap doesn't matter much for the one-person, run-it-yourself project this
started as. It will start to matter as items 1 through 3 get worked on, and it
matters most for anyone new picking this up cold — a contributor reading
`lib/edit.py` for the first time has to reconstruct the shape of `cfg` and
`shots` from usage rather than from anywhere written down.

Not a rewrite of `README.md`'s user-facing walkthrough — a plain description
of the machinery underneath it, for the next person (or the next session) who
has to change it.
