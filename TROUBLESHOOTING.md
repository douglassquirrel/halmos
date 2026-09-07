# When something goes wrong

**Everything here is safe to re-run.** Neither command undoes finished work, and
clips that already exist are never paid for twice.

**Run `python3 0_check.py` first.** Several of the rows below (missing ffmpeg,
missing libass, missing google-genai, missing key) are things it catches for
free, before you spend any time on a real run.

| What you see | What it means | What to do |
|---|---|---|
| `No API key found` | halmos looked in `~/.config/halmos/key` and in the `GEMINI_API_KEY` environment variable and found neither | Follow "A Google API key" in `README.md`. The message itself prints the two lines to paste |
| `... exists but has no key in it` | The key file is there but empty, or still says `YOUR-KEY-HERE` | Put the real key on the first line and save |
| `RESOURCE_EXHAUSTED`, mentions **quota** | You have used today's allowance of video clips (ten per model per day on a new account) | Nothing is lost. Wait until tomorrow and run `python3 2_make.py` again — it carries on from where it stopped |
| `RESOURCE_EXHAUSTED`, mentions **prepayment credits** | The Google account is out of money | Top it up at aistudio.google.com. Nothing was charged |
| `429` errors coming quickly | Too many requests per minute (the limit is two) | Wait five minutes and re-run. Do not run two copies at once |
| `ffmpeg is not installed` | Missing program | See README, "Before you start" |
| `No option name near '...ass...'` during `2_make.py`'s final step | Your `ffmpeg` was built without the caption-rendering library | On a Mac, `brew install ffmpeg-full` (plain `brew install ffmpeg` doesn't include it). `python3 0_check.py` catches this before you get this far — or check for yourself with `ffmpeg -filters \| grep -E "ass\|drawtext"` |
| `Library not loaded: .../libx265...dylib` (or similar) when running `ffmpeg` at all, on a Mac | `ffmpeg-full` is installed but not on your PATH yet — it's a Homebrew "keg-only" formula, so `brew install` alone doesn't put it there, and whatever `ffmpeg` *was* already on your PATH (the plain formula, or a now-mismatched old install) is still what's running | `echo 'export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"' >> ~/.zshrc`, then **open a new terminal window** (it only applies to new windows) and check with `ffmpeg -filters \| grep -E "ass\|drawtext"`. `brew reinstall`/`brew link`/`brew unlink` do **not** fix this on their own — confirmed against a real case, 2026-09-07 |
| `The google-genai package is missing` | Missing add-on | `pip install google-genai` |
| `1 validation error for ImageConfig / image_size / Extra inputs` during `1_plan.py`, the same on every retry | Older versions of this repo's code always asked for a newer `ImageConfig` field (`image_size`) than every installed `google-genai` actually has — this is a code-level mismatch, not a network issue, which is why upgrading the package doesn't fix it | `git pull` to get the current code, which detects whether your installed `google-genai` has that field before asking for it, instead of assuming a version. No `google-genai` upgrade needed |
| `error: externally-managed-environment` while installing google-genai | Your Python came from Homebrew, which blocks plain `pip install` system-wide | `pip3 install --user --break-system-packages google-genai` (see README). Or, if you'd rather not use those flags: `python3 -m venv ~/.halmos-venv && source ~/.halmos-venv/bin/activate && pip install google-genai` — then run halmos's own two commands with that same venv activated |
| `STOPPING: could not generate a picture for: ...` | One or more pictures failed to draw — look at the `FAILED (...)` lines printed above this one for why | Fix whatever those errors are pointing at, then run `python3 1_plan.py` again — it only retries the missing pictures, not the ones that already worked. Nothing else was written this run |
| `style_block.txt still has the placeholder text` | The look has not been described yet | Edit `style_block.txt`. See `STYLE.md` |
| `script.txt still has the placeholder text` | No script yet | Put your words in `script.txt` |
| `No recording found` | The audio file is not where it is looked for | Save it as `audio/narration.m4a` (or `.mp3` / `.wav`) |
| `Could not find beats [...] in the recording` | A line was skipped or read very differently | Check `narration_script.txt`, re-record the missing part or the whole thing |
| `The beat split changed the wording of your script` | A model error, caught deliberately | Just run `python3 1_plan.py` again |
| `STOPPING. This would spend ...` | The limit in `settings.json` | Raise `max_spend_usd` if you meant to |
| "The sound level is outside the normal range" | Your recording was very quiet or very loud | Usable, but re-record a little closer to the microphone for next time |
| A clip is missing after step 2 | It failed on every model | Run `python3 2_make.py` again; it retries only what is missing |

## Things that are not errors

- **Step 2 goes quiet for a long time.** Each clip takes a minute or two and
  there may be a dozen. It prints a line as each finishes. Half an hour of
  near-silence is normal.
- **A picture is redrawn during step 1.** It checks its own work and redraws
  anything that failed. That is the process working.
- **"found 1 repeated take, removing 5.9s".** It found where you fluffed a line
  and said it again, and kept the good one.

## Starting over

- **New look, same script:** edit `style_block.txt`, delete the `frames` folder,
  run `1_plan.py` again. About 40p.
- **New script entirely:** replace `script.txt`, delete `frames`, `gen`, `work`,
  `plan.json` and `audio/narration*`, run `1_plan.py`.
- **Same everything, just rebuild the video:** delete `out/` and run `2_make.py`.
  Costs nothing — it reuses the clips.
