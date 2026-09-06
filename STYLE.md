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

## Keep it consistent between videos

Once you have a look you like, **stop changing it**. A dozen videos that
obviously come from the same place are worth more than a dozen individually
prettier ones that do not match. The style block is the thing that does that
work, so once it is right, leave it alone.
