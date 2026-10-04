# AP_SkipBo

**Play in the browser: https://lighting8282.github.io/Skip_Bo-Implementation/** (works on phones).
Connect to your Archipelago room, or press *Just play* to play without one.
The desktop client and the web page share the same save, so you can switch between them on one slot.

Skip-Bo as an Archipelago game, built the same way as AP Phase 10: the game is pure
Python that lives inside the apworld, and the client is a CommonClient with an
added Kivy tab.

- `skipbo/game/`: the rules engine (`engine.py`), the computer players and the
  hint/auto planner (`ai.py`), and the ten tables (`tables.py`, with measured win rates)
- `skipbo/client/`: `session.py` maps items to game settings and results to checks
  (no networking, so it can be tested); `context.py` holds the commands and the AP
  connection; `game_manager.py` is the GUI tab
- `docs/`: the web client (GitHub Pages). `docs/src/` is a JavaScript port of the
  engine, AI and session, tested against Python-recorded games
- `skipbo/client/assets/cards/`: Phase 10's generated card art, recoloured by
  band (1-4 blue, 5-8 green, 9-12 red)

## GUI controls

Click a table to start. Click a source (a hand card, your stockpile, or a discard
pile top) and the build piles it fits light up green; click one to play. Click the
selected card again to send it to the first pile it fits. To end your turn, select a
hand card and click one of your discard piles. Hand cards that can be played anywhere
get a green tint.

Buttons: Hint (shown in the tab), Undo (works within a turn, but never past a fresh
draw), Auto turn, Auto game, Mulligan, Spare Wild, Auto-stock (plays a natural
stockpile card automatically when it fits), Forfeit. The store and the tables
(with P/W/D tier marks) are along the bottom, and the table log is on the right.
Keys: 1-7 hand, S stockpile, H hint, U or Ctrl+Z undo, A auto turn, Esc deselect.
