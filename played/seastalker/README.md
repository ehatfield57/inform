# Seastalker

Infocom's Seastalker (1984, release 86), by Stu Galley and Jim Lawrence, one of its two
"junior" adventures. You're a young inventor at the Penrose Research Lab in Frobton. A
monster, the Snark, is battering the undersea Aquadome, so you take your new submarine,
the SCIMITAR, across Frobton Bay and out to sea, unmask a traitor among the Aquadome crew,
and go after the Snark and the man who controls it. 100 points.

## Playing

    python3 ../../zplay.py seastalker.z5

The game asks for your first and last name at the start (the walkthrough uses Charles
Penrose).

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 seastalker.z5

It wins 100/100 ("famous adventurer") in 256 commands, 237 moves. It also wins with seeds
3, 5, 7, 8, 9 and 10. With seeds 2, 4 and 6 you gash your arm in the SCIMITAR's crawl space
(a 1-in-5 chance on each turn there), can't fix the voltage regulator, and the story
branches: Mick Antrim later fixes it himself and asks you a question the walkthrough
doesn't expect.

It was made from `../../solutions/seastalker.txt`, a prose guide, turned into commands and
checked step by step. The routes and timings are different in this release:

- Fix the regulator at once: `enter crawl space`, then `fix voltage regulator with tool`.
  Examining it first is one more turn in which to cut your arm.
- Frobton Bay: the guide's NE, N, N, N, NE runs aground. Instead dive to 5 metres, head
  north up the channel the sonar shows, then dive to 15 metres and head northeast through
  the seawall opening. The `look at sonar` lines are the turns spent getting there.
- The voyage is made at slow speed on autopilot, so that the whale (aim the searchlight to
  starboard) and Commander Bly's sonarphone call come at fixed turns.
- The air supply fails on a timer after you arrive; the walkthrough waits for it.
- Bazooka: it's in the storage room; show it to Commander Bly and she has it mounted.
  Doc Horvak's dart gun: `Doc, put dart gun on extensor claw`.
- Tip's trap for the saboteur: answer his questions (yes to Bly mentioning troublemakers
  and to suspecting Marv, no for Mick and Doc), put the black box back on the sonar
  equipment in the comm centre, and send Marv to check it.
- The final fight follows the guide exactly, ending with the guide's single line
  `w then aim bazooka at power pod then shoot power pod with bazooka`. Typed as three
  separate commands it's too slow, and Thorpe fires first.

### An interpreter fix

`go to SCIMITAR` from inside the Aquadome made `zplay.py` stop with "Stack underflow". The
game itself has the bug: one routine pops a value it never pushed. Frotz and Infocom's own
interpreters read the routine's last local variable in that case and carry on, so
`zplay.py` now does the same.

## Files

| File | |
|------|---|
| `seastalker.z5` | the game |
| `walkthrough.txt` | the full solution, 256 commands, 100/100 with `--seed 1` |
| `seastalker_walkthrough.txt` | a full transcript of the walkthrough winning |
| `seastalker.auto.map.pdf` | a map of the 14 places the walkthrough visits (drawn with `../../tools/zplaymap.py`); the voyages at sea aren't rooms, so they don't appear |
| `seastalker.auto.map.json` | the map data behind it |
| `seastalker.txt` | the story of the game, told by Charles |
