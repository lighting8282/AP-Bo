"""Record whole Python games for the JS port to replay.

Every call the game makes on its random source -- random(), choice() and
shuffle() -- is logged with its result. The JS test plays the same setup with
a scripted source that hands back exactly those results, then compares the
full event log and the final state. Any rule or AI difference shows up as the
first event where the two disagree.

    python tools/export_traces.py            # writes docs/test/traces.json
"""

from __future__ import annotations

import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apbo"))

from game import ai  # noqa: E402
from game.engine import Seat, Table  # noqa: E402

OUT = ROOT / "docs" / "test" / "traces.json"
GAMES = 120


class RecordingRandom:
    """Wraps random.Random rather than subclassing it: overriding random() on
    a subclass makes Random route its own shuffle through it, so the recording
    would record itself."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self.log: list = []

    def random(self) -> float:
        value = self._rng.random()
        self.log.append(["r", value])
        return value

    def choice(self, seq):
        index = self._rng.randrange(len(seq))
        self.log.append(["c", index])
        return seq[index]

    def shuffle(self, x) -> None:
        self._rng.shuffle(x)
        self.log.append(["s", list(x)])


def one_game(seed: int) -> dict:
    setup_rng = random.Random(seed * 7919)
    n = setup_rng.randint(2, 4)
    levels = [setup_rng.choice(ai.LEVELS) for _ in range(n)]
    stocks = [setup_rng.choice([5, 10, 15, 20, 30]) for _ in range(n)]
    hand_sizes = [setup_rng.choice([5, 5, 6, 7]) for _ in range(n)]
    slots = [setup_rng.choice([1, 2, 3, 4, 4]) for _ in range(n)]
    bonus = {i: setup_rng.choice([0, 0, 1, 2, 4]) for i in range(n)}

    rng = RecordingRandom(seed)
    seats = [Seat(f"S{i}", [], hand_size=hand_sizes[i], discard_slots=slots[i]) for i in range(n)]
    table = Table.deal(rng, seats, stocks, bonus_wilds=bonus)
    ai.autoplay(table, levels)
    return {
        "seed": seed,
        "levels": levels, "stocks": stocks, "handSizes": hand_sizes, "slots": slots,
        "bonus": {str(k): v for k, v in bonus.items()},
        "rng": rng.log,
        "events": [[e.seat, e.text] for e in table.events],
        "final": {
            "state": table.state.value, "winner": table.winner, "turns": table.turns,
            "builds": table.builds,
            "seats": [{"stock": s.stock, "hand": s.hand, "discards": s.discards,
                       "stockPlayed": s.stock_played, "wildsPlayed": s.wilds_played,
                       "pilesCompleted": s.piles_completed, "cardsPlayed": s.cards_played}
                      for s in seats],
        },
    }


def main() -> int:
    games = [one_game(seed) for seed in range(1, GAMES + 1)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(games, separators=(",", ":")), encoding="utf-8")
    events = sum(len(g["events"]) for g in games)
    print(f"{OUT.relative_to(ROOT)}: {len(games)} games, {events} events, "
          f"{OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
