# halmos

**Your words and your voice in; a finished video out.**

Give halmos a paragraph of text and a recording of yourself reading it. It gives
you back a finished vertical video — about a minute long, with pictures,
captions, and music — ready to post.

**You run two commands.** In between, you look at some pictures and record
yourself reading. That is the whole thing.

It costs **about £7 a video** and takes **about 45 minutes of your time**, spread
over an hour or two of the computer working on its own.

Everything is done by Google's Gemini models. You need one API key from Google
and nothing else. **You never need to open a chatbot**, and no part of this asks
you to write a prompt.

This README is written for someone who has never used a terminal before. If that
is not you, the whole of it is: put a key in `~/.config/halmos/key`, put your
words in `script.txt`, describe your look in `style_block.txt` (or copy one out
of `styles/`), then `python3 1_plan.py`, record the narration it asks for, and
`python3 2_make.py`.

## Getting it

```
git clone https://github.com/douglassquirrel/halmos.git
cd halmos
```

Or download the ZIP from the GitHub page and unzip it. Everything you need is in
the folder; there is nothing to install except the two things below.

---

# Before you start (once, about twenty minutes)

## 1. Two programs

Open a terminal — on a Mac, press ⌘-Space, type "Terminal", press Enter — and
paste these in one at a time to check what you have:

```
python3 --version
ffmpeg -version
```

If either says "command not found":

- **Python** — download from python.org and install it.
- **ffmpeg** — on a Mac, install Homebrew from brew.sh, then run
  `brew install ffmpeg-full`. (Plain `brew install ffmpeg` is missing the
  caption-rendering library halmos needs, and `2_make.py` will fail at the
  very last step after generating everything else — `ffmpeg-full` has
  everything.) On Windows, download from ffmpeg.org. On Linux,
  `sudo apt install ffmpeg`.

**`ffmpeg -version` succeeding is not enough** — it only proves ffmpeg is
installed, not that it has the two libraries halmos needs. Check for those
directly:

```
ffmpeg -filters | grep -E "ass|drawtext"
```

You should see two lines back, one mentioning "libass" and one mentioning
"libfreetype". If you see only one, or none, you have the plain formula —
install `ffmpeg-full` as above (or your system's equivalent full build).

Then install the one add-on this uses:

```
pip install google-genai
```

If that says "command not found", try `pip3` instead of `pip`. If it refuses
with a message about an **"externally managed environment"** — common if your
Python came from Homebrew rather than python.org — paste this instead:

```
pip3 install --user --break-system-packages google-genai
```

(Those two flags are Homebrew's own suggested way past that message, for
installing one library like this rather than a whole project's worth. See
`TROUBLESHOOTING.md` for another way, if you'd rather not use them.)

## 2. A Google API key

1. Go to **aistudio.google.com** and sign in with a Google account.
2. Click **Get API key**, then **Create API key**.
3. **Turn on billing.** This is not optional — the video model has no free tier
   and will simply refuse to work without it. Put about **£20** of credit on the
   account. That is enough for two videos with room for mistakes.
4. Copy the key.

Now put the key in your home folder — **not in this folder**. Open a Terminal
window and paste these two lines, with your own key in place of `YOUR-KEY-HERE`:

```
mkdir -p ~/.config/halmos
printf %s 'YOUR-KEY-HERE' > ~/.config/halmos/key && chmod 600 ~/.config/halmos/key
```

That is all. Every video you ever make with halmos will find it there; you never
do this step again.

*On Windows*, create the file `.config\halmos\key` inside your user folder and
put the key on the first line. Or, on any system, set an environment variable
called `GEMINI_API_KEY` instead — halmos looks there first.

**Why not just keep it in this folder?** Because folders get copied, zipped,
emailed and put on GitHub, and keys go with them. Yours lives somewhere those
things never reach.

**Keep that key private.** It can spend money. Do not email it, do not paste it
into a chat window, do not put it in a shared folder. If you think someone else
has seen it, go back to aistudio.google.com, delete the key and make a new one —
it takes ten seconds and costs nothing. Nothing in halmos ever copies your key
anywhere, prints it, or writes it into any output.

## 3. Your look

Open **`style_block.txt`** and describe how you want your videos to look. This
text is sent with every single picture, which is what makes them all look like
they belong together.

**Do not start from the blank page.** The `styles` folder has three complete,
working looks — flat vector, ink and watercolour, and clay models on a tabletop.
Copy whichever is closest over `style_block.txt`:

```
cp styles/flat-vector.txt style_block.txt
```

and then change the four colours it names to yours. That is a perfectly good way
to finish this step in a minute.

**Read `STYLE.md` before you write your own.** It is short, and it explains the
one thing that surprises everybody: what you *forbid* matters more than what you
describe. Leave the prohibitions at the bottom of the file alone unless you have
a reason to change them.

## 4. Optional settings

Open **`settings.json`** if you want to change the video's name, the mood of the
music, or the spending limit. It is fine to leave it exactly as it is.

## 5. Check your setup

```
python3 0_check.py
```

This looks for everything above — both programs, the caption and labelling
libraries inside ffmpeg, and your API key — and tells you everything that's
missing in one go, rather than one surprise at a time partway through a real
run. It costs nothing and makes no network call. If it says everything is
in place, you are ready for the next section.

---

# Making a video

## Step 1 — Write your script

Open **`script.txt`** and replace it with about **130 words** of your own — that
comes out around sixty seconds when spoken. Write it as you would say it. Do not
describe any pictures; that is done for you.

**Check your facts before this point.** Nothing here will check them for you, and
a confident video repeating something untrue is worse than no video.

## Step 2 — Run the first command

```
python3 1_plan.py
```

Two minutes, about 40p. It breaks your script into short beats, invents a picture
for each one, draws them, checks its own work, and redraws anything that came out
wrong.

You get three things:

- **`contact_sheet.png`** — all the pictures, with a label on each.
- **`narration_script.txt`** — your script, laid out to read aloud.
- **`corrections.txt`** — where you say if a picture is wrong.

## Step 3 — Look at the pictures

Open `contact_sheet.png`. For each picture ask: **does it actually say what that
line of my script says?** Not "is it pretty" — does it carry the meaning.

If any are wrong, open `corrections.txt` and write one line for each, like:

```
3a: too abstract, show an actual open door
5b: there is writing on the sign
```

Say what is **wrong**. You do not have to say what to draw instead.

**This is the cheapest moment in the whole process to change your mind.** A
picture costs 3p to redraw here. The same change after step 5 costs about £7.

If they all look fine, skip this and leave `corrections.txt` alone.

## Step 4 — Record yourself

Open `narration_script.txt` and read it aloud, recording as you go. Your phone's
voice memo app is perfectly good.

Four things:

- **Pause about one second between each numbered line.** That is the only thing
  this asks of you. Everything else adapts to how you speak.
- **Read at whatever pace feels natural.**
- **If you fluff a line, pause and say it again.** The bad take is found and
  removed automatically. You never need to start over.
- **Speak close to the microphone, in a quiet room.**

Then put the file in this folder, in the `audio` folder, named `narration` —
so `audio/narration.m4a`. (`.mp3` and `.wav` work too.)

## Step 5 — Run the second command

```
python3 2_make.py
```

**About forty minutes and £7.** Most of that is waiting while each clip is
generated, which takes a minute or two each. **It prints a line as each one
finishes** — if it looks quiet, it is still working.

It applies your corrections, listens to your recording and works out how long
each beat took, removes any fluffed takes, generates a video clip for every shot,
writes some music, picks the best few seconds of each clip, and builds the
finished file.

You get **`out/yourname.mp4`**.

## Step 6 — Watch it

**All the way through, with the sound on, before you put it anywhere.**

This is the one step nothing can do for you. It has caught things every other
check missed.

---

# Making more than one video

Everything above assumes one video per copy of this folder. If you make more
than a couple, that gets old fast — so both commands take flags that let one
copy of halmos handle any number of separate video projects, each in its own
folder elsewhere on your computer:

```
python3 1_plan.py  --script ~/videos/bees/script.txt \
                   --style  ~/videos/house-style.txt \
                   --out    ~/videos/bees

python3 2_make.py  --project ~/videos/bees
```

`--out` is the project folder — everything `1_plan.py` writes (pictures,
`plan.json`, and so on) goes there instead of into this folder, and it is
created for you if it doesn't exist yet. `2_make.py --project` points at that
same folder to pick up where `1_plan.py` left off; it also finds the style
`1_plan.py` used automatically, so you don't have to repeat `--style`.

`--style` is worth pointing at a file outside any one project folder, like
`~/videos/house-style.txt` above — that is how the same look stays consistent
across every video without copying `style_block.txt` between projects.

Leave all three flags off and both commands work exactly as in the walkthrough
above, using this folder as the only project there is.

---

# If something goes wrong

`TROUBLESHOOTING.md` has the common errors and what they mean. The two you are
most likely to hit:

- **"quota" or "RESOURCE_EXHAUSTED"** — you have used today's allowance of video
  clips. Nothing is lost. Wait until tomorrow and run `python3 2_make.py` again;
  it carries on from where it stopped and does not pay twice for clips it already
  made.
- **"prepayment credits are depleted"** — the account is out of money. Top it up
  at aistudio.google.com. Nothing was charged.

**Everything is safe to re-run.** Neither command undoes work that is already
done.

---

# What is in halmos

| | |
|---|---|
| `README.md` | This file. |
| `LICENSE` | MIT. Do what you like with it. |
| `STYLE.md` | How to describe your look, and what to forbid. Read before editing `style_block.txt`. |
| `RULES.md` | Honesty rules. Short, and they matter if the video is for a business. |
| `TROUBLESHOOTING.md` | Errors and what to do about them. |
| `ARCHITECTURE.md` | How the pipeline actually works, for contributors. Not needed to use halmos. |
| `style_block.txt` | **Your look.** You edit this. |
| `styles/` | Three finished looks. Copy one over `style_block.txt` rather than starting from nothing. |
| `script.txt` | **Your words.** You edit this. |
| `settings.json` | Name, music mood, spending limit. |
| `corrections.txt` | Written for you by step 1; you edit it if a picture is wrong. |
| `0_check.py` | Checks your setup is ready. Run it first, and whenever in doubt. |
| `1_plan.py`, `2_make.py` | The two commands. |
| `lib/` | The machinery. Nothing to change in here. |
| `spend.log` | Every charge, as it happens, so you always know what a video cost. |

---

# What it costs

Measured on a real video made this way:

| | |
|---|---|
| Working out the beats and pictures | £0.05 |
| 13 still pictures | £0.35 |
| Listening to your recording | £0.01 |
| 12 video clips | £6.76 |
| Music | £0.06 |
| **Total** | **about £7.20** |

`settings.json` has a spending limit — £16 by default — and both commands stop
before crossing it rather than after.

---

# About this project

**halmos is MIT-licensed** — see `LICENSE`. Use it, change it, sell what you make
with it. There is no warranty; the money it spends is spent on your Google
account, so read "What it costs" above and set `max_spend_usd` in
`settings.json` to a number you would not mind losing.

**It is not affiliated with Google or Anthropic.** It is a set of scripts that
call the public Gemini API, and the model names in `lib/media.py` are the ones
that worked when it was written. Google renames and retires models; if a model
name stops working, that file is the one place to change it.

**Everything it generates is AI-generated**, and Google marks it as such with an
invisible watermark. `RULES.md` is short and is about what you owe the people who
watch the result. Please read it once.

## Contributing

Issues and pull requests are welcome. Three things worth knowing before you
open one:

- **Run it before you change it.** Almost every bug in this project's history was
  invisible in the code and obvious the first time someone ran the thing — a
  contact sheet that quietly showed one picture instead of twelve, a judgement
  step that silently fell back to a default for every shot, audio three seconds
  longer than the video. Reading was not enough in any of those cases.
- **Never commit a key.** halmos reads yours from `~/.config/halmos/key` or the
  `GEMINI_API_KEY` environment variable, and there is deliberately nowhere inside
  the folder to put one. Please keep it that way.
- **Running the test suite.** `pip install -r requirements-dev.txt`, then
  `pytest --cov=lib --cov-report=term-missing` and `ruff check .` — see
  `TODO.md` for what's covered. CI runs both on every push.

`TODO.md` lists what is known to be missing.
