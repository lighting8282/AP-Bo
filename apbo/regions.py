from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Region

from .data import TABLE_COUNT

if TYPE_CHECKING:
    from .world import BoWorld


def create_and_connect_regions(world: BoWorld) -> None:
    def region(name: str) -> Region:
        r = Region(name, world.player, world.multiworld)
        world.multiworld.regions.append(r)
        return r

    menu = region("Menu")
    # The Lobby holds the cumulative milestones: they count play at any
    # table, so they need nothing but a seat somewhere.
    menu.connect(region("Lobby"), "Menu to Lobby")
    menu.connect(region("Store"), "Menu to Store")
    for t in range(1, TABLE_COUNT + 1):
        menu.connect(region(f"Table {t}"), f"Menu to Table {t}")
    menu.connect(region("Victory"), "Menu to Victory")
