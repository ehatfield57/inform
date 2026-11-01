# Moonmist

Infocom's Moonmist (1986, release 4), by Stu Galley and Jim Lawrence, an introductory-level
mystery. You're a young American detective visiting your friend Tamara at Tresyllian
Castle in Cornwall, where a ghostly White Lady is haunting the halls and someone seems to
be trying to kill her. A recording of the late Lord Lionel sets the guests hunting for his
hidden treasure.

The game has **four versions**, chosen by the favourite colour you give at the gate. Each
one has its own clues, treasure, ghost and villain:

| Colour | Treasure | Hidden in | The ghost | Arrested |
|--------|----------|-----------|-----------|----------|
| red | a war club | a cane in the foyer's umbrella stand | Deirdre, alive | Lord Jack, for murdering Lionel |
| blue | a fossil skull | the bell on the fighting deck | Vivien | Vivien |
| green | Moonmist, a drug | the inkwell in the office | Dr. Wendish | Dr. Wendish, for two murders |
| yellow | a black pearl necklace | a walled-up crypt in the basement | Tamara | Tamara, for fraud |

There's no score. Each case is won by finding the treasure, unmasking the ghost, finding
evidence and arresting the villain; the game then says "You've won the game!"

## Playing

    python3 ../zplay.py moonmist.z5

## The walkthroughs

One per colour, each played from the very start:

    python3 ../zplay.py --script walkthrough.red.txt moonmist.z5
    python3 ../zplay.py --script walkthrough.blue.txt moonmist.z5
    python3 ../zplay.py --script walkthrough.green.txt moonmist.z5
    python3 ../zplay.py --script walkthrough.yellow.txt moonmist.z5

Each one wins with any seed: all four were checked with seeds 1 to 20. The detective is
called Sir Charles Penrose; type another name on the third line if you like (the game
wants a title, first and last name).

They were made from `../solutions/moonmist.red.txt`, `.blue.txt`, `.green.txt` and
`.yellow.txt`, checked step by step, with `../solutions/moonmist.txt` for background.
Changes from the guides:

- The guests wander the castle and stop you to say hello, so a `go to <room>` can end
  early. Where that happens the walkthroughs simply say `go to <room>` twice (the second is
  harmless if the first got there).
- Searches can be interrupted by someone walking past ("Do you want to keep searching?").
  The walkthroughs answer `yes` a few extra times after the searches where that happens;
  spare answers do nothing.
- Dinner: after `wait until 7:54` Tamara calls everyone in, so the walkthrough answers
  `no` to "keep waiting?", goes to the dining room, and reads Bolitho's note a few
  minutes later, when he puts it on Jack's napkin.
- Red: the ghost turns up one turn after 12:41, so there's a `look` before talking to it.
- Blue: the lantern is in the kitchen (the guide goes the wrong way), and the ghost
  appears at 12:13 with a blowgun, so the aerosol has to be used at once.
- Green: the guide's route depends on where Dr. Wendish happens to be. Here you search his
  medical kit directly (`look in kit` twice), and at the end wait in his room until he
  comes in to complain, then arrest him.
- Yellow: look under Tamara's bed twice (journal, then receipt) before she walks in and
  stops you.

## Files

| File | |
|------|---|
| `moonmist.z5` | the game |
| `walkthrough.red.txt`, `.blue.txt`, `.green.txt`, `.yellow.txt` | the four solutions, 110-123 commands each |
| `moonmist_red_walkthrough.txt` (and blue, green, yellow) | full transcripts of each one winning |
| `moonmist_red.auto.map.pdf` (and blue, green, yellow) | maps of the route each walkthrough takes (drawn with `../tools/zplaymap.py`) |
| `moonmist_red.auto.map.json` (and blue, green, yellow) | the map data behind them |
| `moonmist.txt` | the story of the game, told by Sir Charles: the arrival and dinner once, then all four cases |

The maps show the walkthroughs' own moves, and many of them are `go to <room>` jumps
across the castle, so each map shows about 22 rooms joined by those jumps rather than a
full floor plan.
