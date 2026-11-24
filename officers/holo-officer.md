# Standing orders: Holo Officer

The Holo Officer is an image model, not a reader, so these orders are for whoever WRITES its prompts
(NEXUS, Duet, a script). The code checks prompts against the banned-words list below and flags hits
in the gate.

## Prompt rules
1. Describe only what the camera sees: subject, action, setting, light, lens, mood.
2. Never say what the image is FOR. "Website hero", "banner", "landing page", "ad", "poster" make it
   draw a fake website or ad with gibberish text. (Lesson 2026-11-16: both roofing test images came
   back as fake web pages with a "TOULSA" logo.)
3. No business names, town names or slogans. They turn into garbled text. Show place through
   scenery instead (red-brick houses, oak trees, flat plains).
4. End photo prompts with "no text, no lettering, no signage" and keep it.
5. Wide images for page headers: 1344x768. Square: 1024x1024. Portrait: 768x1344.
6. Z-Image Turbo spells short words well (it wrote "NEXUS" right), so text on purpose is fine for
   one or two short words in quotes. Anything longer, add it later in HTML.

## Lessons from the field
NEXUS adds a dated line here each time an image job goes wrong. These are rules too.
- 2026-11-17: "ornate gothic power armour" plus "forge hall" drew medieval knight plate. Spell out the
  sci-fi parts: bulky ceramite plates, oversized rounded shoulder pads, backpack power unit, starship deck.
- 2026-11-17: Holo is text-only. Describing a real person gets a lookalike type, not their face. A real
  likeness needs a reference photo: use `--face` (ReActor swap, personal use only). Still describe the
  person's hair and beard in the prompt so the head shape matches the swapped face.
- 2026-11-17: `--motion` at 2 seconds gave only a glance. For a real move use `--motion-seconds 4` and strong
  words ("turns his head fully to his left and pauses"), plus "only his head moves, body stays still".
- 2026-11-17: Wan only half obeys how far a turn goes. Asked for three-quarter turns, it still went near
  side-on to his left and ended turned right, not facing the camera. Try a new seed rather than more words.
- 2026-11-18: Crew portraits. "Hood of cables and pale crystals" drew one giant crystal spire on the head:
  say "small crystals set in a cabled collar behind the head". "Image-recording camera" drew a modern camera:
  say "boxy brass picture-recorder with a long lens and gothic engraving". "Floating skull" drew one on a stand:
  say "hovering in mid-air, no stand". "Cathedral-like warships" drew floating chandeliers: say "long dark
  armoured battleships with spires and lit gun decks". "Left shoulder pad dark gunmetal" was ignored, both
  came out red. Extra weapons can double up (engineer 2 got two axes): pick the best of 2.
- 2026-11-18 (round 2): "one single axe in his right hand, left hand empty" fixed the double axe. Brass
  picture-recorder and battleship wording worked. Still ignored: a different-coloured shoulder pad, and a
  "hovering" skull came out hanging on a chain. "Brass bionic left hand" gave two bionic hands. A plain
  "fleet admiral" reads Napoleonic, not sci-fi: add greatcoat, machinery and gothic tech to push it.
- 2026-11-18 (round 3): what worked. Grip: "his right armoured fist clenched tightly around the haft, holding the
  axe diagonally across his chest". One ship: "one single battleship ... only one ship in view". A 40k servo-skull:
  "yellowed skull, brass gears bolted into its cranium, two short melted red wax candles on top, glowing red lens
  in one eye socket, hovering with no chain and no stand". Run 3 takes for hard poses; 1 in 3 can block a face.
- 2026-11-18 (round 4): "nothing floating in the air around him" removed the servo-skull cleanly. The flesh right
  hand / bionic left hand split only landed 1 time in 6; usually both hands come out bionic. Expect to pick for it.

## Banned words (gate flags these)
website, web page, webpage, hero, banner, landing page, homepage, header image, logo, ad, advert,
poster, flyer, brochure, mockup, UI
