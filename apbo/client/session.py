"""The bridge between Archipelago and the table.

Pure Python, no networking and no Kivy: received item names go in, a dealt
Table and the location IDs it earned come out. The context does the talking;
this does the deciding, so it can be tested without a server.

Checks are reported as they happen, not at the end of a game: completing a
build pile or reaching a stockpile milestone mid-game sends at once.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any

from ..data import (
    BASE_DISCARD_PILES, BASE_HAND_SIZE, DISCARD_PILE, GAMES_WON_MILESTONES, HAND_SIZE,
    LOCATION_NAME_TO_ID, LOCKED_DISCARD, MIN_STOCK, MULLIGAN, PILES_MILESTONES, RIVAL_WILD,
    SHRINK_STEP, BO_CARD, SPARE_WILD, STACK_STEP, STACKED_STOCK, STOCK_PLAYED_MILESTONES,
    STOCK_SHRINK, STORE_PRICES, TABLE_COUNT, TABLE_UNLOCK, TIERS, AP_POINT, games_won_name,
    piles_name, stock_played_name, store_gate, store_location_name, table_location_name,
)
from ..game import ai
from ..game.cards import WILD
from ..game.engine import Event, Seat, State, Table
from ..game.tables import TABLES

PAYLOAD_VERSION = 1
HUMAN = 0

GOAL_TABLE_TEN, GOAL_ALL_TABLES, GOAL_GAMES_WON = 0, 1, 2


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _tables(values) -> set[int]:
    return {t for t in values if _is_int(t) and 1 <= t <= TABLE_COUNT}


@dataclass
class Stats:
    """Everything that has to survive a reconnect. Lives in Data Storage."""
    games_played: int = 0
    games_won: int = 0
    stock_played: int = 0
    piles: int = 0
    tables_won: set[int] = field(default_factory=set)
    tables_dominant: set[int] = field(default_factory=set)
    tables_piled: set[int] = field(default_factory=set)
    traps_used: dict[str, int] = field(default_factory=dict)
    fillers_used: dict[str, int] = field(default_factory=dict)
    bought: set[int] = field(default_factory=set)
    history: list[dict] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "version": PAYLOAD_VERSION,
            "games_played": self.games_played, "games_won": self.games_won,
            "stock_played": self.stock_played, "piles": self.piles,
            "tables_won": sorted(self.tables_won),
            "tables_dominant": sorted(self.tables_dominant),
            "tables_piled": sorted(self.tables_piled),
            "traps_used": self.traps_used, "fillers_used": self.fillers_used,
            "bought": sorted(self.bought), "history": self.history[-50:],
        }

    @classmethod
    def from_payload(cls, data: Any) -> "Stats | None":
        """None for anything malformed: a payload is untrusted."""
        try:
            if not isinstance(data, dict) or data.get("version") != PAYLOAD_VERSION:
                return None
            # Strict, and the same rules as docs/src/session.js: a save is
            # untrusted, and both clients must refuse the same ones.
            ints = {k: data[k] for k in ("games_played", "games_won", "stock_played", "piles")}
            if any(not _is_int(v) or v < 0 for v in ints.values()):
                return None
            for key in ("traps_used", "fillers_used"):
                if not isinstance(data[key], dict) or not all(map(_is_int, data[key].values())):
                    return None
            lists = ("tables_won", "bought", "tables_dominant", "tables_piled", "history")
            if any(not isinstance(data.get(k, []), list) for k in lists):
                return None
            return cls(
                **ints,
                tables_won=_tables(data["tables_won"]),
                tables_dominant=_tables(data.get("tables_dominant", [])),
                tables_piled=_tables(data.get("tables_piled", [])),
                traps_used={str(k): int(v) for k, v in dict(data["traps_used"]).items()},
                fillers_used={str(k): int(v) for k, v in dict(data["fillers_used"]).items()},
                bought={b for b in data["bought"] if _is_int(b)},
                history=[h for h in data.get("history", []) if isinstance(h, dict)][-50:],
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class Result:
    table: int
    won: bool
    dominant: bool
    stock_left: int
    turns: int
    winner: str | None

    def __str__(self) -> str:
        if self.won:
            extra = " -- dominant!" if self.dominant else ""
            return f"You won at Table {self.table} in {self.turns} turns{extra}"
        if self.winner:
            return f"{self.winner} won Table {self.table}; you had {self.stock_left} stockpile card(s) left"
        return f"Table {self.table} was called with nobody out"


class BoSession:
    def __init__(self, slot_data: dict | None = None, rng: random.Random | None = None) -> None:
        slot_data = slot_data or {}
        self.goal = int(slot_data.get("goal", GOAL_TABLE_TEN))
        self.games_to_win = int(slot_data.get("games_to_win", 10))
        self.tiers = TIERS[: int(slot_data.get("checks_per_table", 2))]
        self.store_slots = int(slot_data.get("store_slots", 0))
        self.death_link = bool(slot_data.get("death_link", 0))
        self.rng = rng or random.Random()

        self.counts: dict[str, int] = {}
        self.stats = Stats()
        self.table: Table | None = None
        self.table_number: int | None = None
        self.levels: list[str] = []
        self.last_result: Result | None = None
        #: Locations already reported, so a check is never queued twice.
        self.reported: set[int] = set()
        self._undo: list[tuple[Table, int]] = []
        self.mulligan_open = False
        self.auto_stock = False
        self.trap_notes: list[str] = []
        #: Bumps per game so the client can tell a new log from an undone one.
        self.game_id = 0

    # -- items -------------------------------------------------------------
    def set_items(self, names: list[str]) -> None:
        counts: dict[str, int] = {}
        for name in names:
            counts[name] = counts.get(name, 0) + 1
        self.counts = counts

    def count(self, name: str) -> int:
        return self.counts.get(name, 0)

    @property
    def unlocked_tables(self) -> set[int]:
        return {t for t in range(1, TABLE_COUNT + 1) if self.count(TABLE_UNLOCK.format(t))}

    @property
    def discard_piles(self) -> int:
        return min(4, BASE_DISCARD_PILES + self.count(DISCARD_PILE))

    @property
    def hand_size(self) -> int:
        return BASE_HAND_SIZE + min(2, self.count(HAND_SIZE))

    @property
    def bonus_wilds(self) -> int:
        return min(4, self.count(BO_CARD))

    def stock_size(self, table: int) -> int:
        return max(MIN_STOCK, TABLES[table].stock - SHRINK_STEP * min(3, self.count(STOCK_SHRINK)))

    def pending(self, name: str) -> int:
        """Traps and fillers received but not yet spent."""
        used = self.stats.traps_used.get(name, 0) + self.stats.fillers_used.get(name, 0)
        return max(0, self.count(name) - used)

    @property
    def power(self) -> int:
        return sum(self.count(n) for n in (DISCARD_PILE, HAND_SIZE, BO_CARD, STOCK_SHRINK))

    # -- store -------------------------------------------------------------
    @property
    def points(self) -> int:
        return self.count(AP_POINT)

    @property
    def points_left(self) -> int:
        return self.points - sum(STORE_PRICES[s - 1] for s in self.stats.bought)

    def can_buy(self, slot: int) -> str | None:
        if not 1 <= slot <= self.store_slots:
            return f"There is no store slot {slot}."
        if slot in self.stats.bought:
            return "Already bought."
        if self.points < store_gate(slot):
            return f"Opens once you have received {store_gate(slot)} AP Points."
        if self.points_left < STORE_PRICES[slot - 1]:
            return f"Costs {STORE_PRICES[slot - 1]}; you have {self.points_left} unspent."
        return None

    def buy(self, slot: int) -> int:
        refusal = self.can_buy(slot)
        if refusal:
            raise RuntimeError(refusal)
        self.stats.bought.add(slot)
        return LOCATION_NAME_TO_ID[store_location_name(slot)]

    # -- a game ------------------------------------------------------------
    def can_play(self, table: int) -> str | None:
        if table not in TABLES:
            return f"Pick a table from 1 to {TABLE_COUNT}."
        if table not in self.unlocked_tables:
            return f"Table {table} is not unlocked yet."
        if self.table is not None and self.table.state is State.PLAYING:
            return "Finish (or /forfeit) the current game first."
        return None

    def start(self, table: int) -> Table:
        refusal = self.can_play(table)
        if refusal:
            raise ValueError(refusal)
        spec = TABLES[table]
        notes = []

        stock = self.stock_size(table)
        if self.pending(STACKED_STOCK):
            self._spend_trap(STACKED_STOCK)
            stock += STACK_STEP
            notes.append(f"Stacked Stockpile: +{STACK_STEP} cards on your stockpile")
        slots = self.discard_piles
        if self.pending(LOCKED_DISCARD) and slots > 1:
            self._spend_trap(LOCKED_DISCARD)
            slots -= 1
            notes.append("Locked Discard: one of your discard piles is closed this game")
        rival = 0
        if self.pending(RIVAL_WILD):
            self._spend_trap(RIVAL_WILD)
            rival = 1
            notes.append("Rival Wild: every opponent starts with a wild")

        seats = [Seat("You", [], hand_size=self.hand_size, discard_slots=slots)]
        seats += [Seat(f"CPU {i + 1}", []) for i in range(len(spec.opponents))]
        bonus = {HUMAN: self.bonus_wilds}
        bonus.update({i: rival for i in range(1, len(seats))})
        self.table = Table.deal(self.rng, seats, [stock] + [spec.stock] * len(spec.opponents),
                                bonus_wilds=bonus)
        self.table_number = table
        self.game_id += 1
        self.levels = ["hard", *spec.opponents]
        self.last_result = None
        self._undo = []
        self.mulligan_open = True
        self.trap_notes = notes
        return self.table

    def _spend_trap(self, name: str) -> None:
        self.stats.traps_used[name] = self.stats.traps_used.get(name, 0) + 1

    def _spend_filler(self, name: str) -> None:
        self.stats.fillers_used[name] = self.stats.fillers_used.get(name, 0) + 1

    @property
    def my_turn(self) -> bool:
        t = self.table
        return t is not None and t.state is State.PLAYING and t.current == HUMAN

    def require_turn(self) -> Table:
        if self.table is None or self.table.state is not State.PLAYING:
            raise RuntimeError("No game in progress. Start one with /play <table>.")
        if self.table.current != HUMAN:
            raise RuntimeError("It is not your turn.")
        return self.table

    def _snapshot(self) -> None:
        self._undo.append((copy.deepcopy(self.table), self.table.refills))

    @property
    def can_undo(self) -> bool:
        return bool(self._undo) and self.my_turn and self._undo[-1][1] == self.table.refills

    def undo(self) -> None:
        if not self.can_undo:
            raise RuntimeError("Nothing to undo (undo never crosses a fresh draw or a discard).")
        self.table = self._undo.pop()[0]

    def play(self, source, build: int) -> None:
        table = self.require_turn()
        self._snapshot()
        refills = table.refills
        try:
            table.play(source, build)
        except RuntimeError:
            self._undo.pop()
            raise
        self.mulligan_open = False
        if table.refills != refills:
            self._undo = []  # new cards were seen
        self._after_human_action()

    def discard(self, hand_index: int, pile: int) -> None:
        table = self.require_turn()
        table.discard(hand_index, pile)
        self._undo = []
        self.mulligan_open = False
        self.run_opponents()

    def run_opponents(self) -> None:
        ai.autoplay(self.table, self.levels, until_seat=HUMAN)
        self._after_human_action()

    def _after_human_action(self) -> None:
        table = self.table
        if self.auto_stock and table.state is State.PLAYING and table.current == HUMAN:
            # QoL: the stockpile card is the whole game, so a natural that
            # fits goes up by itself. Wilds on the stockpile still wait for you.
            seat = table.seat
            while table.state is State.PLAYING and seat.stock_top not in (None, WILD):
                fit = [b for b in range(4) if table.fits(seat.stock_top, b)]
                if not fit:
                    break
                self._undo = []
                table.play(("stock", 0), fit[0])

    def auto_turn(self) -> None:
        table = self.require_turn()
        self._undo = []
        ai.take_turn(table, "hard")
        self.mulligan_open = False
        self.run_opponents()

    def auto_game(self) -> None:
        self.require_turn()
        self._undo = []
        ai.autoplay(self.table, self.levels)

    def hint(self) -> str:
        table = self.require_turn()
        plan = ai.best_plan(table, "hard")
        if plan:
            kind, value, build = plan[0]
            what = (f"your {('W' if value == WILD else value)} from hand" if kind == "hand"
                    else "your stockpile card" if kind == "stock"
                    else f"the top of discard pile {value + 1}")
            reaches = " -- it opens up your stockpile" if plan[-1][0] == "stock" and kind != "stock" else ""
            return f"Play {what} onto build {build + 1}{reaches}."
        i, p = ai.choose_discard(table, "hard")
        return (f"Nothing worth playing. Discard your {table.seat.hand[i] or 'W'} "
                f"onto discard pile {p + 1}.")

    def mulligan(self) -> None:
        table = self.require_turn()
        if not self.mulligan_open:
            raise RuntimeError("A mulligan is only allowed before your first move.")
        if not self.pending(MULLIGAN):
            raise RuntimeError("You have no Mulligans.")
        seat = table.seat
        keep_wilds = seat.hand.count(WILD)
        table.draw_pile[:0] = [c for c in seat.hand if c != WILD]
        seat.hand = [WILD] * keep_wilds
        table.rng.shuffle(table.draw_pile)
        table._refill(seat)
        self._spend_filler(MULLIGAN)
        self.mulligan_open = False
        self._undo = []

    def spare_wild(self) -> None:
        table = self.require_turn()
        if not self.pending(SPARE_WILD):
            raise RuntimeError("You have no Spare Wilds.")
        table.seat.hand.append(WILD)
        self._spend_filler(SPARE_WILD)
        self._undo = []

    def forfeit(self) -> None:
        if self.table is None or self.table.state is not State.PLAYING:
            raise RuntimeError("No game in progress.")
        self.table.state = State.STALLED
        self.table.winner = None
        self.table.events.append(Event(HUMAN, "forfeits"))

    @property
    def game_over(self) -> bool:
        return self.table is not None and self.table.state is not State.PLAYING

    def settle(self) -> Result | None:
        """Bank a finished game into the stats. Idempotent."""
        table = self.table
        if table is None or table.state is State.PLAYING or self.last_result is not None:
            return self.last_result
        me = table.seats[HUMAN]
        won = table.winner == HUMAN
        spec = TABLES[self.table_number]
        dominant = won and all(len(s.stock) * 2 >= spec.stock for s in table.seats[1:])
        self.stats.games_played += 1
        self.stats.stock_played += me.stock_played
        self.stats.piles += me.piles_completed
        if me.piles_completed:
            self.stats.tables_piled.add(self.table_number)
        if won:
            self.stats.games_won += 1
            self.stats.tables_won.add(self.table_number)
        if dominant:
            self.stats.tables_dominant.add(self.table_number)
        self.last_result = Result(
            self.table_number, won, dominant, len(me.stock), table.turns,
            table.seats[table.winner].name if table.winner is not None else None)
        self.stats.history.append({"table": self.table_number, "won": won,
                                   "dominant": dominant, "left": len(me.stock)})
        self._undo = []
        return self.last_result

    # -- checks ------------------------------------------------------------
    def _live(self) -> tuple[int, int]:
        """Stockpile cards and piles this game, not yet banked."""
        if self.table is None or self.last_result is not None:
            return 0, 0
        me = self.table.seats[HUMAN]
        return me.stock_played, me.piles_completed

    def earned(self) -> set[int]:
        """Every location the player has earned so far."""
        names: list[str] = []
        live_stock, live_piles = self._live()
        stock = self.stats.stock_played + live_stock
        piles = self.stats.piles + live_piles
        names += [games_won_name(n) for n in GAMES_WON_MILESTONES if self.stats.games_won >= n]
        names += [stock_played_name(n) for n in STOCK_PLAYED_MILESTONES if stock >= n]
        names += [piles_name(n) for n in PILES_MILESTONES if piles >= n]
        piled = set(self.stats.tables_piled)
        if live_piles:
            piled.add(self.table_number)
        names += [table_location_name(t, "Pile Completed") for t in piled]
        names += [table_location_name(t, "Won") for t in self.stats.tables_won]
        names += [table_location_name(t, "Dominant") for t in self.stats.tables_dominant]
        names += [store_location_name(s) for s in self.stats.bought]
        valid = {table_location_name(t, tier) for t in range(1, TABLE_COUNT + 1) for tier in self.tiers}
        return {LOCATION_NAME_TO_ID[n] for n in names
                if not n.startswith("Table ") or n in valid}

    def new_checks(self) -> list[int]:
        fresh = sorted(self.earned() - self.reported)
        self.reported.update(fresh)
        return fresh

    @property
    def goal_met(self) -> bool:
        if self.goal == GOAL_TABLE_TEN:
            return 10 in self.stats.tables_won
        if self.goal == GOAL_ALL_TABLES:
            return len(self.stats.tables_won) == TABLE_COUNT
        return self.stats.games_won >= self.games_to_win

    @property
    def goal_text(self) -> str:
        if self.goal == GOAL_TABLE_TEN:
            return "Goal: win at Table 10"
        if self.goal == GOAL_ALL_TABLES:
            return f"Goal: win at every table ({len(self.stats.tables_won)}/{TABLE_COUNT})"
        return f"Goal: win {self.games_to_win} games ({self.stats.games_won}/{self.games_to_win})"
