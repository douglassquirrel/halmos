# Describing your look

Open `style_block.txt` and describe how you want your videos to look. That text
is sent with **every single picture and clip**, which is what makes them all look
like they belong to the same channel rather than eleven unrelated images.

You can put anything you like there. What follows is not a house style — it is
what was learned about *getting a model to do as it is told*, which applies
whatever look you choose.

---

## Write about materials and light, not about feelings

Models respond to physical description. "Warm and friendly" gives you almost
nothing; "cut paper on a linen background, lit flat from directly above, deep
shadows" gives you something you can repeat.

Say, concretely:

- **What it is made of.** Paper, clay, ink on cartridge paper, felt, glass,
  pencil, oil paint, plastic toys, chalk on slate.
- **How it is lit.** Flat and even, a single hard light from the left, soft
  window light, glowing from within.
- **The camera.** Straight down from above, eye level, slightly high looking
  down. Whether it moves. (Static is easier to make consistent.)
- **The colours.** Name three or four and say all of them should appear in every
  shot. Without that instruction the palette drifts, and it drifts more on the
  larger models, not less.

## Then say what must NOT be there

**This is the part that surprises people, and it is the single most useful thing
on this page.**

When a shot comes back wrong, adding more description almost never fixes it.
Adding an explicit prohibition usually fixes it first try.

The reason seems to be that a style description leaves gaps, and the model fills
every gap from its own habits. **A prohibition removes a habit. A longer
description does not, because the habit was never competing with your
description — it was filling the silence around it.**

Real examples, each of which cost a wasted clip to discover:

| What was asked for | What arrived | What fixed it |
|---|---|---|
| "gentle 16mm film grain" | The **film strip itself** — sprocket holes, frame numbers, edge markings drawn into the picture | "no sprocket holes, no perforations, no film borders, no frame numbers" |
| a sequence of actions in one shot | A **grid of comic panels** | "one single continuous image, not a grid of panels, no dividing lines" |
| a machine altering its own settings | Cards being **fed into it** by an unseen operator | "nothing enters or leaves the frame, nobody present" |
| nothing about text | The invented words **"DATA SET A"**, and a **wrong date** on an object | "no words, no letters, no numbers, no labels, no writing on anything" |
| nothing about hands | **Bare human hands** reaching in to move things | "no photographic human hands, arms or bodies; objects move by themselves" |

The prohibitions already at the bottom of `style_block.txt` are those five.
**Keep them unless you have a specific reason not to.** If your style genuinely
wants hands, delete that line — but delete it deliberately.

### Two ways a prohibition fails

Prohibitions are reliable, but not magic, and both of these were found by
running the three example looks rather than by reasoning about them.

**It fails if your own description asks for the thing.** The watercolour example
originally said "the paper grain and its soft deckled texture clearly visible"
at the top and "no deckled or torn paper edge" at the bottom. The model obeyed
the description and drew a sheet of paper with ragged edges sitting on a
background — a picture of a painting rather than a painting. Deleting the word
"deckled" from the *description* fixed in one go what the prohibition could not.
**When a shot keeps coming back wrong, read your own positive lines first.** A
prohibition cannot win an argument with them.

**It weakens when the subject itself implies the thing.** A weather vane
implies compass letters. Told five separate times to draw no letters, the model
went from four letters to two, and would not go to none. Nothing about the style
was wrong; the object was pulling harder than the sentence. This is exactly what
the automatic frame check and rule 5 in `RULES.md` — a person watches the whole
video before it goes out — are there to catch. If it happens to you, the cheap
fix is to change the *object* in that one shot, not to add a sixth prohibition.

## Show, do not describe, when you can

Words are obeyed by some models and quietly ignored by others. **A picture is
never ignored.**

This is already built in: every video clip is generated from its own still image
as a first frame, so the look is pinned by a picture rather than by a paragraph.
One model, given a style description that said "deliberately handmade, not
photorealistic" in those exact words, returned a photorealistic image — and then
matched the style perfectly when handed the still instead.

It means two things for you:

- **Judge your style from the contact sheet, not from the wording.** If the
  pictures look right, the style block is right.
- **Changing your look is cheap.** Edit `style_block.txt` and run `1_plan.py`
  again — new pictures cost about 40p. Do that as many times as you like before
  you record anything.

## Three looks you can just take

Writing one of these from scratch is the hardest part of setting halmos up, and
you have nothing to look at while you do it. So there are three finished ones in
the **`styles`** folder. Each is complete and works as it stands:

| File | What it looks like | Best at |
|---|---|---|
| `styles/flat-vector.txt` | Solid shapes of flat colour, no outlines, long soft shadows | Clean and modern; reads well small, on a phone. Pick this if unsure |
| `styles/ink-and-watercolour.txt` | Dip-pen line and transparent washes on cream cartridge paper | Warm and personal rather than corporate; forgiving of imperfection |
| `styles/clay-tabletop.txt` | Plasticine models on a grey table, real shadows, thumbprints visible | Showing a *process* — things with weight move legibly |

To use one, copy it over `style_block.txt`:

```
cp styles/flat-vector.txt style_block.txt
```

Then change the palette line to your own colours and leave everything else
alone. Every one of them names exactly four colours and says all four must
appear in every shot — that line is doing more work than it looks like, and it
is the first thing to edit and the last thing to delete.

## Keep it consistent between videos

Once you have a look you like, **stop changing it**. A dozen videos that
obviously come from the same place are worth more than a dozen individually
prettier ones that do not match. The style block is the thing that does that
work, so once it is right, leave it alone.
