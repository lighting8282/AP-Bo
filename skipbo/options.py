from dataclasses import dataclass

from Options import Choice, DeathLink, OptionGroup, PerGameCommonOptions, Range

from .data import MAX_STORE_SLOTS, TABLE_COUNT


class Goal(Choice):
    """
    What finishes your game.

    table_ten:  win at Table 10, the three-hard-opponent, 30-card table.
    all_tables: win at every one of the ten tables.
    games_won:  win `games_to_win` games, at any tables.
    """
    display_name = "Goal"
    option_table_ten = 0
    option_all_tables = 1
    option_games_won = 2
    default = option_table_ten


class GamesToWin(Range):
    """With goal: games_won, how many wins finish the game."""
    display_name = "Games To Win"
    range_start = 3
    range_end = 20
    default = 10


class StartingTables(Range):
    """How many tables are unlocked from the start. Easy tables are handed out
    first, so the opening is winnable before any power item arrives."""
    display_name = "Starting Tables"
    range_start = 1
    range_end = 3
    default = 2


class ChecksPerTable(Range):
    """
    How many checks each table holds. A prefix of:

    1: complete a build pile there
    2: also win there
    3: also win while every opponent still holds half their stockpile
    """
    display_name = "Checks Per Table"
    range_start = 1
    range_end = 3
    default = 2


class DiscardPileItems(Range):
    """You start with two discard piles; each item opens another (max four)."""
    display_name = "Extra Discard Pile Items"
    range_start = 0
    range_end = 2
    default = 2


class HandSizeItems(Range):
    """Each item adds one card to your hand (base five)."""
    display_name = "Hand Size Upgrade Items"
    range_start = 0
    range_end = 2
    default = 2


class SkipBoCardItems(Range):
    """Each item deals you a wild Skip-Bo card at the start of every game,
    on top of your hand size."""
    display_name = "Skip-Bo Card Items"
    range_start = 0
    range_end = 4
    default = 3


class StockShrinkItems(Range):
    """Each item takes two cards off your stockpile (never below five).
    Opponents' stockpiles are unaffected."""
    display_name = "Stockpile Shrink Items"
    range_start = 0
    range_end = 3
    default = 3


class TrapChance(Range):
    """
    Percentage chance that any filler item is replaced by a trap. Traps apply
    to your next game only:

    Stacked Stockpile: three extra cards on your stockpile
    Locked Discard:    one of your discard piles is closed
    Rival Wild:        every opponent starts with a wild in hand
    """
    display_name = "Trap Chance"
    range_start = 0
    range_end = 100
    default = 10


class StoreSlots(Range):
    """How many checks the store sells for AP Points. 0 turns it off."""
    display_name = "Store Slots"
    range_start = 0
    range_end = MAX_STORE_SLOTS
    default = 4


class SkipBoDeathLink(DeathLink):
    """A death is a lost game. When someone else dies, your current game is
    forfeited; when you lose a game, everyone linked dies."""


@dataclass
class SkipBoOptions(PerGameCommonOptions):
    goal: Goal
    games_to_win: GamesToWin
    starting_tables: StartingTables
    checks_per_table: ChecksPerTable
    discard_pile_items: DiscardPileItems
    hand_size_items: HandSizeItems
    skipbo_card_items: SkipBoCardItems
    stock_shrink_items: StockShrinkItems
    store_slots: StoreSlots
    trap_chance: TrapChance
    death_link: SkipBoDeathLink


option_groups = [
    OptionGroup("Goal", [Goal, GamesToWin, StartingTables, ChecksPerTable, StoreSlots]),
    OptionGroup("Power Items", [DiscardPileItems, HandSizeItems, SkipBoCardItems,
                                StockShrinkItems]),
    OptionGroup("Extras", [TrapChance, SkipBoDeathLink]),
]

option_presets = {
    "quick": {"goal": Goal.option_games_won, "games_to_win": 5, "checks_per_table": 1,
              "starting_tables": 3, "store_slots": 2, "trap_chance": 0},
    "marathon": {"goal": Goal.option_all_tables, "checks_per_table": 3,
                 "starting_tables": 1, "store_slots": MAX_STORE_SLOTS, "trap_chance": 30},
}

assert TABLE_COUNT == 10
