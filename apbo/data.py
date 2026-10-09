"""Names and IDs shared by the world and the client.

Free of Archipelago imports so the client's pure logic can be tested without
a checkout, and so the two sides read one table and cannot drift apart.
"""

from __future__ import annotations

#: The Archipelago game identifier. archipelago.json and the docs filename
#: carry their own copies; test_data checks they agree.
GAME_NAME = "AP_Bo"

#: Kept as a literal so this module stays dependency-free; test_data asserts
#: it matches game.tables.
TABLE_COUNT = 10

TABLE_UNLOCK = "Table {} Unlocked"

DISCARD_PILE = "Extra Discard Pile"
HAND_SIZE = "Hand Size Upgrade"
BO_CARD = "Bo Card"
STOCK_SHRINK = "Stockpile Shrink"

#: The four items that make a table winnable. Logic counts them together:
#: measured, each is worth roughly the same to the win rate, so asking for
#: "any N of these" is honest and gives fill far more freedom than naming one.
POWER_ITEMS = [DISCARD_PILE, HAND_SIZE, BO_CARD, STOCK_SHRINK]

STACKED_STOCK = "Stacked Stockpile"
LOCKED_DISCARD = "Locked Discard"
RIVAL_WILD = "Rival Wild"

MULLIGAN = "Mulligan"
SPARE_WILD = "Spare Wild"

AP_POINT = "AP Point"

TRAPS = [STACKED_STOCK, LOCKED_DISCARD, RIVAL_WILD]
FILLERS = [MULLIGAN, SPARE_WILD]

#: Every seat but yours starts with the full four. You start with two, and
#: each Extra Discard Pile item opens one more.
BASE_DISCARD_PILES = 2
BASE_HAND_SIZE = 5
#: Cards each Stockpile Shrink takes off your stockpile.
SHRINK_STEP = 2
#: Your stockpile never goes below this, however many shrinks arrive.
MIN_STOCK = 5
#: Cards a Stacked Stockpile trap adds to your next game.
STACK_STEP = 3

#: Hard caps on how many copies of each power item can be useful.
POWER_CAPS = {DISCARD_PILE: 2, HAND_SIZE: 2, BO_CARD: 4, STOCK_SHRINK: 3}

ITEM_NAME_TO_ID = {
    **{TABLE_UNLOCK.format(t): t for t in range(1, TABLE_COUNT + 1)},
    DISCARD_PILE: 50,
    HAND_SIZE: 51,
    BO_CARD: 52,
    STOCK_SHRINK: 53,
    STACKED_STOCK: 60,
    LOCKED_DISCARD: 61,
    RIVAL_WILD: 62,
    MULLIGAN: 70,
    SPARE_WILD: 71,
    AP_POINT: 72,
}

#: Per-table checks, most earnable first: `checks_per_table` takes a prefix.
#:   Pile Completed  finish a build pile (play its 12) at that table
#:   Won             empty your stockpile first
#:   Dominant        win while every opponent still holds half their stockpile
TIERS = ["Pile Completed", "Won", "Dominant"]

#: Cumulative checks across every table. They gate on nothing, which is what
#: gives a seed a workable opening.
GAMES_WON_MILESTONES = [1, 2, 3, 5, 8, 12, 16, 20]
STOCK_PLAYED_MILESTONES = [10, 25, 50, 100, 150, 200]
PILES_MILESTONES = [1, 3, 6, 10, 15, 25]

STORE_PRICES = [1, 1, 1, 1, 2, 2, 3, 3]
MAX_STORE_SLOTS = len(STORE_PRICES)
STORE_SLACK = 2


def store_gate(slot: int) -> int:
    """Points needed before slot `slot` (1-based) may be bought. The sum of
    the cheapest prices, so any purchase order satisfies the logic."""
    return sum(STORE_PRICES[:slot])


def store_points(slots: int) -> int:
    return sum(STORE_PRICES[:slots]) + STORE_SLACK if slots else 0


def table_location_name(table: int, tier: str) -> str:
    return f"Table {table} - {tier}"


def games_won_name(n: int) -> str:
    return f"Games Won: {n}"


def stock_played_name(n: int) -> str:
    return f"Stockpile Cards Played: {n}"


def piles_name(n: int) -> str:
    return f"Build Piles Completed: {n}"


def store_location_name(slot: int) -> str:
    return f"Store Slot {slot}"


LOCATION_NAME_TO_ID = {
    **{
        table_location_name(t, tier): 100 + t * 10 + i
        for t in range(1, TABLE_COUNT + 1)
        for i, tier in enumerate(TIERS)
    },
    **{games_won_name(n): 300 + i for i, n in enumerate(GAMES_WON_MILESTONES)},
    **{stock_played_name(n): 330 + i for i, n in enumerate(STOCK_PLAYED_MILESTONES)},
    **{piles_name(n): 360 + i for i, n in enumerate(PILES_MILESTONES)},
    **{store_location_name(s): 500 + s for s in range(1, MAX_STORE_SLOTS + 1)},
}

MILESTONE_NAMES = (
    [games_won_name(n) for n in GAMES_WON_MILESTONES]
    + [stock_played_name(n) for n in STOCK_PLAYED_MILESTONES]
    + [piles_name(n) for n in PILES_MILESTONES]
)
