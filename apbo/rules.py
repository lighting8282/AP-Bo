"""Access rules, from measured win rates (see game/tables.py).

A table's unlock only seats you; what the measurements gate is *winning*
there, so requirements live on the locations. Power is counted across all
four power items together -- in simulation each copy moved win rates by a
similar amount, so "any N of them" is the honest rule and leaves fill free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rule_builder.rules import Has, HasAll, HasFromList, Rule

from .data import (
    AP_POINT, POWER_ITEMS, TABLE_COUNT, TABLE_UNLOCK, store_gate, store_location_name,
    table_location_name,
)
from .options import Goal

if TYPE_CHECKING:
    from .world import BoWorld

#: Power needed to *win* at each table. Base win rates (no items): 1, 2, 4
#: are 85%+, 3 and 6 are ~45%, 5, 7, 8 ~30%, 9 and 10 ~25% with a much
#: steeper fall-off on the Dominant tier.
WIN_POWER = {1: 0, 2: 0, 4: 0, 3: 2, 6: 2, 5: 4, 7: 4, 8: 4, 9: 6, 10: 6}
#: Dominant asks for this much more on top.
DOMINANT_EXTRA = 2

#: The most power any location asks for. The pool must carry at least this.
MAX_POWER_NEEDED = max(WIN_POWER.values()) + DOMINANT_EXTRA

EASY_TABLES = frozenset(t for t, p in WIN_POWER.items() if p == 0)


def power(count: int) -> Rule | None:
    return HasFromList(*POWER_ITEMS, count=count) if count else None


def tier_requirement(table: int, tier: str) -> Rule | None:
    if tier == "Pile Completed":
        return None
    if tier == "Won":
        return power(WIN_POWER[table])
    return power(WIN_POWER[table] + DOMINANT_EXTRA)


def set_all_rules(world: BoWorld) -> None:
    for t in range(1, TABLE_COUNT + 1):
        world.set_rule(world.get_entrance(f"Menu to Table {t}"), Has(TABLE_UNLOCK.format(t)))
        for tier in world.tiers:
            rule = tier_requirement(t, tier)
            if rule is not None:
                world.set_rule(world.get_location(table_location_name(t, tier)), rule)
        rule = power(WIN_POWER[t])
        if rule is not None:
            world.set_rule(world.get_location(f"Table {t} Won (event)"), rule)

    for slot in range(1, int(world.options.store_slots) + 1):
        world.set_rule(world.get_location(store_location_name(slot)),
                       Has(AP_POINT, count=store_gate(slot)))

    goal = world.options.goal
    if goal == Goal.option_table_ten:
        goal_rule: Rule = Has("Table 10 Win")
    elif goal == Goal.option_all_tables:
        goal_rule = HasAll(*(f"Table {t} Win" for t in range(1, TABLE_COUNT + 1)))
    else:
        # Wins at any table count, and the starting tables are easy ones, so
        # logic has nothing to add: volume is the player's job.
        goal_rule = None
    if goal_rule is not None:
        world.set_rule(world.get_entrance("Menu to Victory"), goal_rule)
    world.set_completion_rule(Has("Victory"))
