# Avatar style — the fleet's portraits (ADR-056 rule 7)

Owned by brand-comms; committed by fabric-coordinator. One look for
every agent, so that a row of avatars on the Fleet Deck or the Board reads
as one family and no single image reads as a person.

## What an avatar is

A painted portrait of an adult, head and shoulders, in warm,
hand-painted anime: clean, confident line work; soft cel shading
laid over watercolour; a soft watercolour background on paper. It is
plainly an illustration. Nobody should be able to take it for a
photograph, and that is part of the disclosure the "AI" prefix makes in
the name (ADR-056 §4).

## Never

- **Never a named studio's style, artist's style or franchise.** No
  studio, director, artist, series or character is named in a prompt,
  in a reason for a choice, or in the file. The style is described only
  in this guide's own words.
- **Never a likeness of the scientist behind the surname.** Never the
  period dress, hairstyle or a portrait pose taken from that person,
  and never an object, plant, animal or instrument tied to their work.
  The surname is a name and nothing in the picture.
- **Never a child.** Every avatar looks like an adult between about 25
  and 45: adult proportions, a jaw and neck that read as adult. Never
  the enlarged eyes and small chin that make a figure read as young.
- **Never text, letters, numbers, logos, badges, insignia or a
  watermark** anywhere in the image, the clothes included.
- **Never a uniform or rank, a weapon, a flag, a religious symbol or
  a national costume.** The face may belong to a culture (below); no
  object, garment or symbol marks a nation, a faith or a group.
- **Never sexualised, never a caricature of an ethnicity.** Clothing is
  ordinary, covered and modern.

## One family: what is the same in every avatar

| | |
|---|---|
| Canvas | Square, 1024 × 1024 PNG, opaque. |
| Framing | Head and shoulders; the face centred horizontally, the eyes on a line about 40 % down from the top; the top of the hair ideally about 12 % below the top edge, never touching it; the shoulders cut by the bottom edge. The whole face sits inside the central circle of 80 % of the width, so a round crop at 32 px loses nothing that matters; the hair may cross that circle. That circle is a check, never drawn: the wash fills the square to its edges, with no frame or ring. |
| Pose | Three-quarter view, turned slightly to the viewer's left; the eyes look at the viewer. |
| Expression | Calm and friendly; a slight, closed-mouth smile. Never laughing, never posed with a hand. |
| Light | One soft, warm light from the upper left, a gentle rim of cool light on the right; no hard shadows, no dramatic contrast. |
| Background | A soft, loose watercolour wash on visible paper grain, no objects, no horizon, no scene: warm amber light (the fabric's `#ffb547`) blooming behind the head on the left, softening into teal (`#2ec4b6`) towards the right and the lower corners, a hint of deep indigo (`#232c63`) only at the very edges. Lighter and more open behind the face than at the edges. |
| Colour | The figure's own colours are muted and natural; the palette's amber and teal may appear once in the clothes, never as a saturated block. |
| Clothes | Simple, modern, everyday: a shirt, a knit, a jacket, a scarf. Plain fabric, no pattern stronger than a soft texture. |

## What differs: the agent's own

- **Sex**, F or M, as the agent chose it (rule 6): for appearance only.
- **Appearance follows the surname's culture** — the entry's `from` in
  `identities/personas/surnames.json`, the same culture the first name
  comes from (ADR-056 rule 5) — so a name, a surname and a face belong
  together and no persona borrows a people's name with another's face.
  Within that, brand-comms chooses per agent the hair (colour, length,
  style), eye colour, skin tone, glasses or not, freckles, and the
  clothes and their colour, so that two agents of one culture still
  look like two people. Plausible, not typical: a person one could meet
  in that country today, never a stereotype of it, never a costume, and
  never the scientist (see "Never").
- The agent may ask for a feature (shorter hair, glasses, another
  colour) when it rejects an image; brand-comms honours it inside
  this guide.

## The prompt

Every avatar is drawn with `fabric-genimage` from this template, with
only `{sex}` and `{appearance}` filled in. The rest is not edited per
agent: a change to it is a change to this guide. The framing circle
is named in the prompt only as something not to paint: given as a
target, the model painted it as a ring (sample 1).

```text
Square portrait avatar illustration, warm hand-painted anime style: clean
confident line work, soft cel shading over watercolour, gentle and warm.
An adult {sex: woman | man} of about 35, with a mature adult face, natural
adult eye size and a defined jaw and neck, {appearance}. Head and
shoulders, face centred, eyes about 40 percent down from the top; generous
empty space above the head, the top of the hair about one eighth of the
way down from the top edge; three-quarter view turned slightly to the left,
eyes looking at the viewer; calm, friendly expression with a slight
closed-mouth smile. One soft warm light from the upper left, a gentle cool
rim light on the right, no hard shadows. Background: a soft loose
watercolour wash on visible paper grain filling the whole square edge to
edge, no frame, no border, no circle or ring, no objects and no scene; warm
amber light blooming behind the head on the left, softening into clear
teal towards the right and the lower corners, a hint of deep indigo only
at the very edges. Muted natural colours on the figure. Simple modern
everyday clothes in plain fabric. No text, no letters, no logos, no
badges, no jewellery beyond small studs, no objects held, nothing in the
hands.
```

Options: `--size 1024x1024 --quality high --background opaque`, output
`/usr/local/share/agent-fabric/avatars/<agent id>/<n>.png`, `<n>`
counting from 1 per agent and never reused.

## Judging a candidate before an agent sees it

brand-comms looks at every image before it is offered and redraws
(a new `<n>`, the old one kept) when any of these fails: it reads as an
adult; nothing of the "Never" list is in it, text included; the framing
and the light match the table; the background is the wash and not a
scene; the face reads at 32 px in a round crop and the hair does not touch the top edge; beside the avatars
already accepted, it belongs to the same family. A generated image is a
candidate, never an approval.

## Changing this guide

A change to the template, the framing or the palette is proposed to the
owner by brand-comms; avatars already accepted are not redrawn for it
unless the owner says so.
