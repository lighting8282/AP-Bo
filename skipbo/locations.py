from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Location

from . import items
from .data import (
    GAME_NAME, LOCATION_NAME_TO_ID, MILESTONE_NAMES, TABLE_COUNT, store_location_name,
    table_location_name,
)

if TYPE_CHECKING:
    from .world import SkipBoWorld


class SkipBoLocation(Location):
    game = GAME_NAME


def _add(region, names: list[str]) -> None:
    region.add_locations({n: LOCATION_NAME_TO_ID[n] for n in names}, SkipBoLocation)


def create_all_locations(world: SkipBoWorld) -> None:
    _add(world.get_region("Lobby"), MILESTONE_NAMES)

    slots = int(world.options.store_slots)
    if slots:
        _add(world.get_region("Store"), [store_location_name(s) for s in range(1, slots + 1)])

    for t in range(1, TABLE_COUNT + 1):
        region = world.get_region(f"Table {t}")
        _add(region, [table_location_name(t, tier) for tier in world.tiers])
        # Winning is an event, so the goal can depend on it whatever the
        # checks_per_table prefix left out.
        region.add_event(f"Table {t} Won (event)", f"Table {t} Win",
                         location_type=SkipBoLocation, item_type=items.SkipBoItem)

    world.get_region("Victory").add_event(
        "Goal", "Victory", location_type=SkipBoLocation, item_type=items.SkipBoItem)
