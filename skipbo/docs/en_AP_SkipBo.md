# AP_SkipBo

## What is this game?

Skip-Bo, played against computer opponents inside the Archipelago client. Build
piles go 1 through 12; play onto them from your hand, your discard piles and your
stockpile. Empty your stockpile first to win.

## What does randomization do?

Ten **tables** are locked behind items. Each seats you against different opponents
(easy, normal or hard computer players) with different stockpile sizes.

Your strength comes from four **power items**:

| Item | Effect |
| --- | --- |
| Extra Discard Pile | You start with 2 discard piles; each opens another (max 4) |
| Hand Size Upgrade | +1 card in hand (base 5) |
| Skip-Bo Card | A wild dealt into your hand at the start of every game |
| Stockpile Shrink | Two fewer cards on your stockpile (min 5) |

Filler: **Mulligan** (redraw your opening hand) and **Spare Wild** (add a wild to
your hand mid-game). Traps hit your next game: **Stacked Stockpile** (+3 stockpile
cards), **Locked Discard** (one discard pile closed), **Rival Wild** (opponents
start with a wild).

## What are the checks?

- Per table, depending on `checks_per_table`: *Pile Completed* (play a 12 there),
  *Won*, *Dominant* (win while every opponent still holds half their stockpile).
- Milestones at any table: games won, stockpile cards played, build piles completed.
- Optional store slots bought with AP Points.

## Goal

Win at Table 10, win at every table, or win a set number of games.
