"""The ten tables: who you sit down against, and how deep the stockpiles are.

Tables replace Phase 10's phases as the thing Archipelago unlocks. They are
not ordered by number in difficulty -- see rules.py for the measured tiers.

Measured win rates for the human seat (played by the hard AI), 150 games
each; "base" is no items with two discard piles, "full" is every power item:

    table  seats            stock   base   full
      1    1 easy             10    100%   100%
      2    2 easy             10     97%   100%
      3    1 normal           10     51%    97%
      4    3 easy             15     85%   100%
      5    2 normal           15     33%    91%
      6    1 hard             15     38%    95%
      7    3 normal           20     25%    84%
      8    2 hard             20     31%    79%
      9    3 hard             25     22%    79%
     10    3 hard             30     27%    76%
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpec:
    number: int
    opponents: tuple[str, ...]  # one AI level per seat
    stock: int

    @property
    def description(self) -> str:
        counts: dict[str, int] = {}
        for level in self.opponents:
            counts[level] = counts.get(level, 0) + 1
        who = ", ".join(f"{n} {level}" for level, n in counts.items())
        plural = "s" if len(self.opponents) > 1 else ""
        return f"vs {who} opponent{plural}, {self.stock}-card stockpiles"


TABLES: dict[int, TableSpec] = {
    spec.number: spec for spec in (
        TableSpec(1, ("easy",), 10),
        TableSpec(2, ("easy", "easy"), 10),
        TableSpec(3, ("normal",), 10),
        TableSpec(4, ("easy", "easy", "easy"), 15),
        TableSpec(5, ("normal", "normal"), 15),
        TableSpec(6, ("hard",), 15),
        TableSpec(7, ("normal", "normal", "normal"), 20),
        TableSpec(8, ("hard", "hard"), 20),
        TableSpec(9, ("hard", "hard", "hard"), 25),
        TableSpec(10, ("hard", "hard", "hard"), 30),
    )
}
