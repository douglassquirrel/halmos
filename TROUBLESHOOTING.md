# When something goes wrong

**Everything here is safe to re-run.** Neither command undoes finished work, and
clips that already exist are never paid for twice.

| What you see | What it means | What to do |
|---|---|---|
| `No API key found` | halmos looked in `~/.config/halmos/key` and in the `GEMINI_API_KEY` environment variable and found neither | Follow "A Google API key" in `README.md`. The message itself prints the two lines to paste |
| `... exists but has no key in it` | The key file is there but empty, or still says `YOUR-KEY-HERE` | Put the real key on the first line and save |
| `RESOURCE_EXHAUSTED`, mentions **quota** | You have used today's allowance of video clips (ten per model per day on a new account) | Nothing is lost. Wait until tomorrow and run `python3 2_make.py` again — it carries on from where it stopped |
| `RESOURCE_EXHAUSTED`, mentions **prepayment credits** | The Google account is out of money | Top it up at aistudio.google.com. Nothing was charged |
| `429` errors coming quickly | Too many requests per minute (the limit is two) | Wait five minutes and re-run. Do not run two copies at once |
| `ffmpeg is not installed` | Missing program | See README, "Before you start" |
| `No option name near '...ass...'` during `2_make.py`'s final step | Your `ffmpeg` was built without the caption-rendering library | On a Mac, `brew install ffmpeg-full` (plain `brew install ffmpeg` doesn't include it) |
| `The google-genai package is missing` | Missing add-on | `pip install google-genai` |
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
