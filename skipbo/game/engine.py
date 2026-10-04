"""The Skip-Bo table: rules only, no AI and no Archipelago.

Everything a seat can do goes through `play` and `discard`, and both check the
rules before touching anything, so the human seat, the computer seats and the
client's undo all share one definition of a legal move.

Rules as printed, with the Archipelago knobs spelled out:
  * four shared build piles, each built 1 -> 12; a wild counts as whatever is
    needed next; a finished pile is set aside and shuffled back in when the
    draw pile runs dry
  * each seat has a stockpile (top card face up), a hand refilled to
    `hand_size` at the start of every turn and again whenever it is played
    empty mid-turn, and up to four discard piles of its own
  * a turn ends by discarding one hand card onto one of your discard piles
  * the first seat to play its last stockpile card wins
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from .cards import MAX_RANK, WILD, Card, card_name, shuffled_deck

BUILD_PILES = 4
MAX_DISCARD_PILES = 4
#: A full table of four seats with five-card hands rarely needs more than
#: ninety turns. Past this something has deadlocked -- every seat stuck
#: discarding with no pile moving -- and the game is called.
TURN_LIMIT = 600


class State(Enum):
    PLAYING = "playing"
    WON = "won"          # winner holds the seat index
    STALLED = "stalled"  # deck exhausted or turn limit hit; nobody wins


@dataclass
class Seat:
    name: str
    stock: list[Card]
    hand_size: int = 5
    discard_slots: int = MAX_DISCARD_PILES
    hand: list[Card] = field(default_factory=list)
    discards: list[list[Card]] = field(
        default_factory=lambda: [[] for _ in range(MAX_DISCARD_PILES)])
    #: Per-game tallies the Archipelago checks read.
    stock_played: int = 0
    wilds_played: int = 0
    piles_completed: int = 0
    cards_played: int = 0

    @property
    def stock_top(self) -> Card | None:
        return self.stock[-1] if self.stock else None

    def discard_top(self, pile: int) -> Card | None:
        stack = self.discards[pile]
        return stack[-1] if stack else None


# A move source: ("hand", index), ("stock", 0) or ("discard", pile).
Source = tuple[str, int]


@dataclass
class Event:
    seat: int
    text: str


class Table:
    def __init__(self, seats: list[Seat], rng: random.Random,
                 deck: list[Card] | None = None) -> None:
        self.seats = seats
        self.rng = rng
        self.draw_pile: list[Card] = deck if deck is not None else []
        self.builds: list[list[Card]] = [[] for _ in range(BUILD_PILES)]
        self.set_aside: list[Card] = []
        self.current = 0
        self.turns = 0
        self.state = State.PLAYING
        self.winner: int | None = None
        self.events: list[Event] = []
        #: Bumps whenever a hand is refilled. Undo must not cross one, since
        #: that would let you look at a card and then take it back.
        self.refills = 0

    # -- setup -------------------------------------------------------------
    @classmethod
    def deal(cls, rng: random.Random, seats: list[Seat], stock_sizes: list[int],
             wilds: int = 18, bonus_wilds: dict[int, int] | None = None) -> "Table":
        """Deal stockpiles and the first hand. `bonus_wilds` grants wilds
        into a seat's opening hand from outside the deck -- the Archipelago
        item, which is a card you are handed, not one shuffled in."""
        deck = shuffled_deck(rng, wilds)
        for seat, size in zip(seats, stock_sizes):
            seat.stock = [deck.pop() for _ in range(size)]
        table = cls(seats, rng, deck)
        for index, extra in (bonus_wilds or {}).items():
            if extra:
                # Dealt on top of the hand, not into it: fill first so the
                # wilds cost the seat no room.
                table._refill(seats[index])
                seats[index].hand.extend([WILD] * extra)
        table._start_turn()
        return table

    # -- queries -----------------------------------------------------------
    @property
    def seat(self) -> Seat:
        return self.seats[self.current]

    def needed(self, build: int) -> int:
        return len(self.builds[build]) + 1

    def fits(self, card: Card, build: int) -> bool:
        return card == WILD or card == self.needed(build)

    def source_card(self, source: Source) -> Card | None:
        kind, index = source
        seat = self.seat
        if kind == "hand":
            return seat.hand[index] if 0 <= index < len(seat.hand) else None
        if kind == "stock":
            return seat.stock_top
        if kind == "discard":
            if 0 <= index < MAX_DISCARD_PILES:
                return seat.discard_top(index)
            return None
        raise ValueError(f"unknown source {kind}")

    def legal_plays(self) -> list[tuple[Source, int]]:
        """Every (source, build) the current seat could play right now."""
        if self.state is not State.PLAYING:
            return []
        seat = self.seat
        sources: list[Source] = [("stock", 0)] if seat.stock else []
        sources += [("hand", i) for i in range(len(seat.hand))]
        sources += [("discard", p) for p in range(MAX_DISCARD_PILES) if seat.discards[p]]
        return [(src, b) for src in sources for b in range(BUILD_PILES)
                if self.fits(self.source_card(src), b)]

    def can_discard_to(self, pile: int) -> bool:
        return 0 <= pile < self.seat.discard_slots

    # -- actions -----------------------------------------------------------
    def play(self, source: Source, build: int) -> Card:
        if self.state is not State.PLAYING:
            raise RuntimeError("The game is over.")
        if not 0 <= build < BUILD_PILES:
            raise RuntimeError(f"There is no build pile {build + 1}.")
        card = self.source_card(source)
        if card is None:
            raise RuntimeError("Nothing to play from there.")
        if not self.fits(card, build):
            raise RuntimeError(
                f"Build pile {build + 1} needs a {self.needed(build)}, not a {card_name(card)}.")

        seat = self.seat
        kind, index = source
        if kind == "hand":
            seat.hand.pop(index)
        elif kind == "stock":
            seat.stock.pop()
        else:
            seat.discards[index].pop()

        value = self.needed(build)
        self.builds[build].append(card)
        seat.cards_played += 1
        if card == WILD:
            seat.wilds_played += 1
        shown = f"W as {value}" if card == WILD else str(value)
        where = {"hand": "hand", "stock": "stockpile", "discard": "a discard pile"}[kind]
        self._log(f"plays {shown} from {where} onto build {build + 1}")

        if value == MAX_RANK:
            self.set_aside.extend(self.builds[build])
            self.builds[build] = []
            seat.piles_completed += 1
            self._log(f"completes build pile {build + 1}")

        if kind == "stock":
            seat.stock_played += 1
            if not seat.stock:
                self.state = State.WON
                self.winner = self.current
                self._log("plays the last stockpile card. Game over!")
                return card

        if not seat.hand:
            self._refill(seat)
        return card

    def discard(self, hand_index: int, pile: int) -> Card:
        """Discard to end the turn."""
        if self.state is not State.PLAYING:
            raise RuntimeError("The game is over.")
        seat = self.seat
        if not 0 <= hand_index < len(seat.hand):
            raise RuntimeError("No such card in hand.")
        if not self.can_discard_to(pile):
            raise RuntimeError(f"Discard pile {pile + 1} is locked.")
        card = seat.hand.pop(hand_index)
        seat.discards[pile].append(card)
        self._log(f"discards {card_name(card)} to pile {pile + 1}")
        self._end_turn()
        return card

    def pass_turn(self) -> None:
        """Only legal with an empty hand the deck cannot refill."""
        if self.seat.hand:
            raise RuntimeError("You must discard to end your turn.")
        self._log("has nothing to discard and passes")
        self._end_turn()

    # -- internals ---------------------------------------------------------
    def _end_turn(self) -> None:
        self.turns += 1
        if self.turns >= TURN_LIMIT:
            self.state = State.STALLED
            self._log("-- the game is called: nobody can finish")
            return
        self.current = (self.current + 1) % len(self.seats)
        self._start_turn()

    def _start_turn(self) -> None:
        self._refill(self.seat)
        if not self.draw_pile and not self.set_aside and not any(
                s.hand for s in self.seats):
            self.state = State.STALLED

    def _refill(self, seat: Seat) -> None:
        while len(seat.hand) < seat.hand_size:
            if not self.draw_pile:
                if not self.set_aside:
                    break
                self.draw_pile = self.set_aside
                self.set_aside = []
                self.rng.shuffle(self.draw_pile)
                self.events.append(Event(-1, "Finished piles are shuffled back into the deck."))
            seat.hand.append(self.draw_pile.pop())
        self.refills += 1

    def _log(self, text: str) -> None:
        self.events.append(Event(self.current, text))
