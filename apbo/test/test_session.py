import random
import unittest

from ..client.session import HUMAN, BoSession, Stats
from ..data import LOCATION_NAME_TO_ID
from ..game import ai
from ..game.engine import Seat, State, Table


def session(**slot) -> BoSession:
    s = BoSession({"checks_per_table": 3, **slot}, random.Random(5))
    s.set_items(["Table 1 Unlocked", "Table 3 Unlocked"])
    return s


class TestSession(unittest.TestCase):
    def test_locked_table_refused(self) -> None:
        self.assertIsNotNone(session().can_play(2))

    def test_autogame_settles_and_earns(self) -> None:
        s = session()
        for _ in range(5):
            s.start(1)
            s.auto_game()
            self.assertIsNotNone(s.settle())
        self.assertGreater(s.stats.games_won, 0)
        earned = s.earned()
        self.assertIn(LOCATION_NAME_TO_ID["Table 1 - Won"], earned)
        self.assertIn(LOCATION_NAME_TO_ID["Games Won: 1"], earned)
        self.assertEqual(s.new_checks(), sorted(earned))
        self.assertEqual(s.new_checks(), [])

    def test_undo_restores(self) -> None:
        s = session()
        plays = []
        for seed in range(60):
            s.rng = random.Random(seed)
            s.table = None
            s.start(1)
            plays = [p for p in s.table.legal_plays() if p[0][0] == "hand"]
            if plays and len(s.table.seat.hand) > 1:
                break
        self.assertTrue(plays)
        before = list(s.table.seat.hand)
        s.play(*plays[0])
        self.assertTrue(s.can_undo)
        s.undo()
        self.assertEqual(s.table.seat.hand, before)
        self.assertFalse(s.can_undo)

    def test_discard_runs_opponents_back_to_you(self) -> None:
        s = session()
        s.start(3)
        s.discard(0, 0)
        self.assertTrue(s.game_over or s.table.current == HUMAN)

    def test_traps_apply_once(self) -> None:
        s = session()
        s.set_items(["Table 1 Unlocked", "Stacked Stockpile", "Locked Discard"])
        t = s.start(1)
        self.assertEqual(len(t.seats[HUMAN].stock), 10 + 3)
        self.assertEqual(t.seats[HUMAN].discard_slots, 1)
        s.forfeit()
        s.settle()
        t = s.start(1)
        self.assertEqual(len(t.seats[HUMAN].stock), 10)
        self.assertEqual(t.seats[HUMAN].discard_slots, 2)

    def test_power_items_change_the_deal(self) -> None:
        s = session()
        s.set_items(["Table 1 Unlocked", "Bo Card", "Bo Card", "Hand Size Upgrade",
                     "Stockpile Shrink", "Extra Discard Pile"])
        t = s.start(1)
        me = t.seats[HUMAN]
        self.assertEqual(len(me.hand), 6 + 2)
        self.assertGreaterEqual(me.hand.count(0), 2)
        self.assertEqual(len(me.stock), 8)
        self.assertEqual(me.discard_slots, 3)

    def test_payload_round_trip_and_rejects_junk(self) -> None:
        s = session()
        s.start(1)
        s.auto_game()
        s.settle()
        again = Stats.from_payload(s.stats.to_payload())
        self.assertEqual(again.to_payload(), s.stats.to_payload())
        for junk in (None, [], {"version": 99}, {"version": 1, "games_won": "x"}):
            self.assertIsNone(Stats.from_payload(junk))

    def test_tiers_respect_checks_per_table(self) -> None:
        s = BoSession({"checks_per_table": 1}, random.Random(1))
        s.stats.tables_won.add(1)
        self.assertNotIn(LOCATION_NAME_TO_ID["Table 1 - Won"], s.earned())

    def test_hint_always_answers(self) -> None:
        s = session()
        s.start(3)
        self.assertTrue(s.hint())


class TestEngine(unittest.TestCase):
    def test_many_games_terminate_and_conserve_cards(self) -> None:
        rng = random.Random(3)
        for _ in range(30):
            seats = [Seat("a", []), Seat("b", []), Seat("c", [])]
            t = Table.deal(rng, seats, [15, 15, 15])
            ai.autoplay(t, ["hard", "normal", "easy"])
            self.assertIsNot(t.state, State.PLAYING)
            total = (len(t.draw_pile) + len(t.set_aside) + sum(map(len, t.builds))
                     + sum(len(s.stock) + len(s.hand) + sum(map(len, s.discards))
                           for s in seats))
            self.assertEqual(total, 162)

    def test_rejects_illegal_play(self) -> None:
        t = Table.deal(random.Random(1), [Seat("a", []), Seat("b", [])], [5, 5])
        t.seat.hand = [7]
        with self.assertRaises(RuntimeError):
            t.play(("hand", 0), 0)
