"""Computer players, and the planner behind Hint and Auto.

Three levels:
  easy    plays what fits directly, never digs through its discards, and
          discards at random -- it wastes most of what it is dealt
  normal  a shallow search for a run of plays that frees its stockpile card
  hard    a deeper search, keeps wilds for when they reach the stockpile,
          stacks its discards in order, and avoids setting up the next seat

The search works on an abstract state -- what each build pile needs, the hand
as a multiset, the discard stacks -- and ends a line the moment the stockpile
card becomes playable, because the next stockpile card is face down and the
plan has to be remade once it shows anyway.
"""

from __future__ import annotations

from collections import Counter

from .cards import MAX_RANK, WILD
from .engine import BUILD_PILES, MAX_DISCARD_PILES, Source, State, Table

LEVELS = ("easy", "normal", "hard")
DEPTH = {"easy": 1, "normal": 3, "hard": 8}
NODE_LIMIT = 6000

# A plan step names a card by value, not hand position: positions shift as
# cards leave the hand, values do not.
Step = tuple[str, int, int]  # (kind, value-or-pile, build)


def _advance(needed: int) -> int:
    return 1 if needed == MAX_RANK else needed + 1


def best_plan(table: Table, level: str = "hard") -> list[Step]:
    """The best line of plays from here, ending at a stockpile play if any
    line reaches one. Empty when nothing is worth playing."""
    seat = table.seat
    depth = DEPTH[level]
    stock = seat.stock_top
    needed0 = tuple(table.needed(b) for b in range(BUILD_PILES))
    hand0 = Counter(seat.hand)
    piles0 = tuple(tuple(seat.discards[p]) for p in range(MAX_DISCARD_PILES))
    nxt = table.seats[(table.current + 1) % len(table.seats)].stock_top
    avoid = level == "hard" and len(table.seats) > 1

    best: tuple[float, list[Step]] = (0.0, [])
    seen: set = set()
    nodes = 0

    def score_end(needed, hand, wilds, from_hand, from_piles) -> float:
        value = from_hand * 2 + from_piles * 2.5 - wilds * 6
        if sum(hand.values()) == 0 and from_hand:
            value += 8  # emptied the hand: a fresh five is coming
        if avoid and nxt is not None:
            value -= 5 * sum(1 for n in needed if nxt == WILD or n == nxt)
        return value

    def search(needed, hand, piles, path, wilds, from_hand, from_piles):
        nonlocal best, nodes
        nodes += 1
        # Stockpile reachable: nothing beats it, so close the line here.
        if stock is not None:
            for b in range(BUILD_PILES):
                if stock == WILD or needed[b] == stock:
                    score = 1000 - wilds * 3 + from_piles + (-1 if stock == WILD else 0)
                    if score > best[0]:
                        best = (score, path + [("stock", 0, b)])
                    return
        score = score_end(needed, hand, wilds, from_hand, from_piles)
        if score > best[0]:
            best = (score, list(path))
        if len(path) >= depth or nodes > NODE_LIMIT:
            return
        key = (needed, tuple(sorted(hand.items())), piles)
        if key in seen:
            return
        seen.add(key)

        for b in range(BUILD_PILES):
            n = needed[b]
            if b and n in needed[:b]:
                continue  # two piles needing the same card are interchangeable
            nn = needed[:b] + (_advance(n),) + needed[b + 1:]
            if hand.get(n):
                hand[n] -= 1
                search(nn, hand, piles, path + [("hand", n, b)], wilds, from_hand + 1, from_piles)
                hand[n] += 1
            for p in range(MAX_DISCARD_PILES):
                if piles[p] and piles[p][-1] in (n, WILD):
                    w = piles[p][-1] == WILD
                    np = piles[:p] + (piles[p][:-1],) + piles[p + 1:]
                    search(nn, hand, np, path + [("discard", p, b)],
                           wilds + w, from_hand, from_piles + 1)
            if hand.get(WILD) and level != "easy":
                hand[WILD] -= 1
                search(nn, hand, piles, path + [("hand", WILD, b)], wilds + 1,
                       from_hand + 1, from_piles)
                hand[WILD] += 1

    if level == "easy":
        return _easy_plan(table)
    search(needed0, hand0, piles0, [], 0, 0, 0)
    return best[1]


def _easy_plan(table: Table) -> list[Step]:
    seat = table.seat
    for b in range(BUILD_PILES):
        if seat.stock_top is not None and table.fits(seat.stock_top, b):
            return [("stock", 0, b)]
    for b in range(BUILD_PILES):
        n = table.needed(b)
        if n in seat.hand and table.rng.random() < 0.6:
            return [("hand", n, b)]
    return []


def resolve(table: Table, step: Step) -> Source:
    kind, value, _ = step
    if kind == "hand":
        return ("hand", table.seat.hand.index(value))
    return (kind, value)


def choose_discard(table: Table, level: str = "hard") -> tuple[int, int]:
    """(hand index, discard pile) to end the turn with."""
    seat = table.seat
    piles = range(seat.discard_slots)
    if level == "easy":
        naturals = [i for i, c in enumerate(seat.hand) if c != WILD] or list(range(len(seat.hand)))
        return table.rng.choice(naturals), table.rng.choice(list(piles))

    stock = seat.stock_top
    best, best_score = (0, 0), float("-inf")
    for i, card in enumerate(seat.hand):
        keep = 0.0
        if card == WILD:
            keep = 40
        elif stock not in (None, WILD) and card < stock:
            # Cards that lead up to the stockpile card are the ones to hold.
            keep = 3 + (stock - card <= 3) * 3
        keep += card in [table.needed(b) for b in range(BUILD_PILES)] and 4 or 0
        for p in piles:
            top = seat.discard_top(p)
            if top is None:
                fit = 4 + (sum(1 for q in piles if not seat.discards[q]) - 1) * 1.5
            elif top == card:
                fit = 8
            elif top == card + 1:
                fit = 7.5
            elif top != WILD and top > card:
                fit = 4 - (top - card) * 0.3
            else:
                fit = -2 - len(seat.discards[p]) * 0.5  # buries a pile
            score = fit - keep + card * 0.05
            if score > best_score:
                best, best_score = (i, p), score
    return best


def take_turn(table: Table, level: str) -> None:
    """Play one whole turn for the current seat."""
    me = table.current
    guard = 0
    while table.state is State.PLAYING and table.current == me and guard < 60:
        guard += 1
        plan = best_plan(table, level)
        if not plan:
            break
        refills = table.refills
        for step in plan:
            table.play(resolve(table, step), step[2])
            if table.state is not State.PLAYING or table.refills != refills:
                break
            if step[0] == "stock":
                break  # a new stockpile card is showing: plan again
        else:
            if plan[-1][0] != "stock":
                break
    if table.state is State.PLAYING and table.current == me:
        if table.seat.hand:
            table.discard(*choose_discard(table, level))
        else:
            table.pass_turn()


def autoplay(table: Table, levels: list[str], until_seat: int | None = None) -> None:
    """Run seats until the game ends, or until it is `until_seat`'s turn."""
    while table.state is State.PLAYING:
        if until_seat is not None and table.current == until_seat:
            return
        take_turn(table, levels[table.current])
