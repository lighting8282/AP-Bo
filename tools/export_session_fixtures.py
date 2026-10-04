"""Record what the Python session decides, for the JS session to match.

Covers the tables shared with the world (item/location IDs, the ten tables),
what a set of received items does to the deal, which location IDs a set of
stats has earned, how saves are read, and how traps are applied at the start
of a game.

    python tools/export_session_fixtures.py   # writes docs/test/session_fixtures.json
"""

from __future__ import annotations

import importlib
import json
import pathlib
import random
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Import skipbo.client.session without skipbo/__init__.py, which needs an
# Archipelago checkout: register an empty package and let the relative
# imports resolve inside it.
pkg = types.ModuleType("skipbo")
pkg.__path__ = [str(ROOT / "skipbo")]
sys.modules["skipbo"] = pkg

data = importlib.import_module("skipbo.data")
tables = importlib.import_module("skipbo.game.tables")
session_mod = importlib.import_module("skipbo.client.session")
sys.path.insert(0, str(ROOT / "tools"))
from export_traces import RecordingRandom  # noqa: E402

OUT = ROOT / "docs" / "test" / "session_fixtures.json"
ALL_ITEMS = list(data.ITEM_NAME_TO_ID)


def random_items(rng: random.Random) -> list[str]:
    return [rng.choice(ALL_ITEMS) for _ in range(rng.randint(0, 40))]


def configs(rng: random.Random) -> list[dict]:
    out = []
    for _ in range(150):
        items = random_items(rng)
        s = session_mod.SkipBoSession({}, random.Random(0))
        s.set_items(items)
        for name in data.TRAPS + data.FILLERS:
            if rng.random() < 0.4:
                bucket = s.stats.traps_used if name in data.TRAPS else s.stats.fillers_used
                bucket[name] = rng.randint(0, 3)
        out.append({
            "items": items,
            "trapsUsed": s.stats.traps_used, "fillersUsed": s.stats.fillers_used,
            "unlocked": sorted(s.unlocked_tables),
            "discardPiles": s.discard_piles, "handSize": s.hand_size,
            "bonusWilds": s.bonus_wilds, "power": s.power, "points": s.points,
            "stockSizes": {t: s.stock_size(t) for t in tables.TABLES},
            "pending": {n: s.pending(n) for n in data.TRAPS + data.FILLERS},
        })
    return out


def earned(rng: random.Random) -> list[dict]:
    out = []
    for _ in range(200):
        slot = {"goal": rng.randint(0, 2), "games_to_win": rng.randint(3, 20),
                "checks_per_table": rng.randint(1, 3), "store_slots": rng.randint(0, 8)}
        s = session_mod.SkipBoSession(slot, random.Random(0))
        st = s.stats
        st.games_won = rng.randint(0, 25)
        st.games_played = st.games_won + rng.randint(0, 10)
        st.stock_played = rng.randint(0, 250)
        st.piles = rng.randint(0, 30)
        st.tables_won = set(rng.sample(range(1, 11), rng.randint(0, 10)))
        st.tables_dominant = set(rng.sample(range(1, 11), rng.randint(0, 4)))
        st.tables_piled = set(rng.sample(range(1, 11), rng.randint(0, 10)))
        st.bought = set(rng.sample(range(1, 9), rng.randint(0, 4)))
        out.append({"slot": slot, "payload": st.to_payload(),
                    "earned": sorted(s.earned()), "goalMet": s.goal_met, "goalText": s.goal_text})
    return out


def payloads() -> list[dict]:
    good = session_mod.Stats(games_played=3, games_won=2, stock_played=40, piles=5,
                             tables_won={1, 4}, tables_dominant={1}, tables_piled={1, 4, 9},
                             traps_used={"Rival Wild": 1}, fillers_used={"Mulligan": 2},
                             bought={1, 2}, history=[{"table": 1, "won": True}]).to_payload()
    cases = [good, None, [], {"version": 99}, {**good, "games_won": -1},
             {**good, "tables_won": [1, 99, 4]}, {**good, "traps_used": []},
             {**good, "history": [1, {"table": 2}]}, {k: v for k, v in good.items() if k != "bought"},
             {**good, "tables_won": [1, "2", 3.5, True]}, {**good, "bought": ["1", 2]},
             {**good, "tables_piled": 5}, {**good, "history": "x"}, {**good, "games_won": True},
             # No 2.0 case: JSON gives JS no way to tell it from 2, and
             # neither client ever writes one.
             {**good, "fillers_used": {"Mulligan": "2"}},
             {k: v for k, v in good.items() if k not in ("tables_dominant", "tables_piled", "history")}]
    out = []
    for case in cases:
        stats = session_mod.Stats.from_payload(case)
        out.append({"input": case, "output": stats.to_payload() if stats else None})
    return out


def starts(rng: random.Random) -> list[dict]:
    out = []
    for seed in range(60):
        items = random_items(rng) + [data.TABLE_UNLOCK.format(t) for t in range(1, 11)]
        table = rng.randint(1, 10)
        rec = RecordingRandom(seed)
        s = session_mod.SkipBoSession({}, rec)
        s.set_items(items)
        t = s.start(table)
        out.append({
            "items": items, "table": table, "rng": rec.log, "notes": s.trap_notes,
            "trapsUsed": s.stats.traps_used, "levels": s.levels,
            "seats": [{"stock": x.stock, "hand": x.hand, "slots": x.discard_slots,
                       "handSize": x.hand_size} for x in t.seats],
        })
    return out


def main() -> int:
    rng = random.Random(2026)
    fixture = {
        "itemIds": data.ITEM_NAME_TO_ID,
        "locationIds": data.LOCATION_NAME_TO_ID,
        "tables": {n: {"opponents": list(t.opponents), "stock": t.stock,
                       "description": t.description} for n, t in tables.TABLES.items()},
        "configs": configs(rng),
        "earned": earned(rng),
        "payloads": payloads(),
        "starts": starts(rng),
    }
    OUT.write_text(json.dumps(fixture, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
