from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Item, ItemClassification

from .data import (
    AP_POINT, FILLERS, GAME_NAME, ITEM_NAME_TO_ID, POWER_ITEMS, TABLE_COUNT, TABLE_UNLOCK, TRAPS,
)

if TYPE_CHECKING:
    from .world import SkipBoWorld

CLASSIFICATIONS = {
    **{TABLE_UNLOCK.format(t): ItemClassification.progression
       for t in range(1, TABLE_COUNT + 1)},
    **{name: ItemClassification.progression for name in POWER_ITEMS},
    **{name: ItemClassification.trap for name in TRAPS},
    **{name: ItemClassification.filler for name in FILLERS},
    AP_POINT: ItemClassification.progression,
}


class SkipBoItem(Item):
    game = GAME_NAME


def create_item(world: SkipBoWorld, name: str) -> SkipBoItem:
    return SkipBoItem(name, CLASSIFICATIONS[name], ITEM_NAME_TO_ID[name], world.player)


def filler_name(world: SkipBoWorld) -> str:
    if world.random.randint(0, 99) < world.options.trap_chance:
        return world.random.choice(TRAPS)
    return world.random.choice(FILLERS)


def power_counts(world: SkipBoWorld) -> dict[str, int]:
    from .data import DISCARD_PILE, HAND_SIZE, SKIPBO_CARD, STOCK_SHRINK
    return {
        DISCARD_PILE: int(world.options.discard_pile_items),
        HAND_SIZE: int(world.options.hand_size_items),
        SKIPBO_CARD: int(world.options.skipbo_card_items),
        STOCK_SHRINK: int(world.options.stock_shrink_items),
    }


def choose_starting_tables(world: SkipBoWorld) -> list[int]:
    from .rules import EASY_TABLES
    easy = sorted(EASY_TABLES)
    world.random.shuffle(easy)
    return easy[: int(world.options.starting_tables)]


def create_all_items(world: SkipBoWorld) -> None:
    capacity = len(world.multiworld.get_unfilled_locations(world.player))

    starting = set(choose_starting_tables(world))
    for t in sorted(starting):
        world.push_precollected(world.create_item(TABLE_UNLOCK.format(t)))

    pool: list[Item] = [world.create_item(TABLE_UNLOCK.format(t))
                        for t in range(1, TABLE_COUNT + 1) if t not in starting]
    pool += [world.create_item(AP_POINT) for _ in range(world.store_points)]
    for name, count in world.power.items():
        pool += [world.create_item(name) for _ in range(count)]

    if len(pool) > capacity:
        from Options import OptionError
        raise OptionError(f"{GAME_NAME}: {len(pool)} required items but only "
                          f"{capacity} locations. Raise checks_per_table or lower store_slots.")
    pool += [world.create_filler() for _ in range(capacity - len(pool))]
    world.multiworld.itempool += pool
