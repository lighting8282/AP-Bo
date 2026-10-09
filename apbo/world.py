from collections.abc import Mapping
from typing import Any

from worlds.AutoWorld import World

from . import items, locations, regions, rules, web_world
from . import options as bo_options
from .data import (
    GAME_NAME, ITEM_NAME_TO_ID, LOCATION_NAME_TO_ID, MILESTONE_NAMES, POWER_CAPS, POWER_ITEMS, TABLE_COUNT, TIERS, store_points,
)


class BoWorld(World):
    """
    AP Bo is a card game of shared build piles: play 1 through 12 onto them,
    from your hand, your discard piles and above all your stockpile, and the
    first player to empty their stockpile wins. Archipelago decides which
    tables you may sit at, and how many discard piles, cards in hand, wilds
    and stockpile cards you play with.
    """

    game = GAME_NAME
    web = web_world.BoWebWorld()

    options_dataclass = bo_options.BoOptions
    options: bo_options.BoOptions

    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_to_id = ITEM_NAME_TO_ID

    store_points: int = 0
    power: dict[str, int]

    @property
    def tiers(self) -> list[str]:
        return TIERS[: int(self.options.checks_per_table)]

    def generate_early(self) -> None:
        # The pool has to carry the most power any location will ask for, or
        # those locations are unreachable. Raise counts toward their caps
        # rather than fail, so every option combination generates.
        self.power = items.power_counts(self)
        needed = max(rules.WIN_POWER.values())
        if "Dominant" in self.tiers:
            needed += rules.DOMINANT_EXTRA
        for name in POWER_ITEMS:
            while sum(self.power.values()) < needed and self.power[name] < POWER_CAPS[name]:
                self.power[name] += 1

        # Trim the store until the required items fit the location count.
        base = TABLE_COUNT * len(self.tiers) + len(MILESTONE_NAMES)
        required = (TABLE_COUNT - int(self.options.starting_tables)) + sum(self.power.values())
        slots = int(self.options.store_slots)
        while slots and required + store_points(slots) > base + slots:
            slots -= 1
        self.options.store_slots.value = slots
        self.store_points = store_points(slots)

    def create_regions(self) -> None:
        regions.create_and_connect_regions(self)
        locations.create_all_locations(self)

    def set_rules(self) -> None:
        rules.set_all_rules(self)

    def create_items(self) -> None:
        items.create_all_items(self)

    def create_item(self, name: str) -> items.BoItem:
        return items.create_item(self, name)

    def get_filler_item_name(self) -> str:
        return items.filler_name(self)

    def fill_slot_data(self) -> Mapping[str, Any]:
        return self.options.as_dict(
            "goal", "games_to_win", "checks_per_table", "store_slots", "death_link",
        )
