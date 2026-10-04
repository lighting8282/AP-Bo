import json
import pathlib

from ..data import GAME_NAME, ITEM_NAME_TO_ID, LOCATION_NAME_TO_ID, TABLE_COUNT
from ..game.tables import TABLES
from . import SkipBoTestBase


class TestDefault(SkipBoTestBase):
    def test_ids_unique(self) -> None:
        self.assertEqual(len(set(ITEM_NAME_TO_ID.values())), len(ITEM_NAME_TO_ID))
        self.assertEqual(len(set(LOCATION_NAME_TO_ID.values())), len(LOCATION_NAME_TO_ID))
        self.assertEqual(len(TABLES), TABLE_COUNT)

    def test_manifest_matches(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        manifest = json.loads((root / "archipelago.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["game"], GAME_NAME)
        self.assertTrue((root / "docs" / f"en_{GAME_NAME}.md").is_file())

    def test_table_ten_needs_power(self) -> None:
        self.collect_by_name(["Table 10 Unlocked"])
        self.assertFalse(self.can_reach_location("Table 10 - Won"))
        self.assertTrue(self.can_reach_location("Table 10 - Pile Completed"))


class TestAllTablesDominant(SkipBoTestBase):
    # Every power option at zero: generate_early must raise them back up.
    options = {"goal": 1, "checks_per_table": 3, "discard_pile_items": 0,
               "hand_size_items": 0, "skipbo_card_items": 0, "stock_shrink_items": 0,
               "store_slots": 8, "starting_tables": 1, "trap_chance": 100}


class TestQuick(SkipBoTestBase):
    options = {"goal": 2, "checks_per_table": 1, "starting_tables": 3, "store_slots": 8}
