"""Visual and interaction check for the AP Bo client tab.

Kivy needs a real window, so this is not a unit test: it opens the client UI
with a seeded session, dispatches real clicks through the widgets, takes a
screenshot and exits.

    <AP checkout>/.venv/Scripts/python.exe tests/ui_check.py out.png
"""

import asyncio
import os
import random
import sys

AP = os.environ.get("AP_ROOT", "C:/Users/turtl/Archipelago")
sys.path.insert(0, AP)
os.chdir(AP)

import ModuleUpdate  # noqa: E402

ModuleUpdate.update_ran = True

OUT = sys.argv[1] if len(sys.argv) > 1 else "apbo_ui.png"

from worlds.apbo.client.context import BoContext  # noqa: E402
from worlds.apbo.client.session import HUMAN, BoSession  # noqa: E402

failures: list[str] = []


def check(condition, message):
    print(f"  {'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def frame_of(widget):
    return widget.parent


async def main():
    ctx = BoContext(None, None)
    ctx.session = BoSession({"checks_per_table": 3, "store_slots": 4}, random.Random(11))
    ctx.session.set_items(["Table 1 Unlocked", "Table 3 Unlocked", "Table 7 Unlocked",
                           "Bo Card", "Extra Discard Pile", "Mulligan", "Spare Wild",
                           "AP Point", "AP Point"])
    ctx.restore_state = "done"
    ctx.run_gui()

    from kivy.clock import Clock
    from kivy.core.window import Window

    def exercise(_dt):
        ui = ctx.ui
        view = ui.game_view
        s = ctx.session
        Window.size = (1400, 900)
        ui.screens.switch_screens(ui.game_tab)
        ui.tabs.set_active_item(ui.game_tab) if hasattr(ui.tabs, "set_active_item") else None
        view.refresh(force=True)

        buttons = list(reversed(view.tables.children))
        check(len(buttons) == 10, "ten table buttons")
        check(buttons[1].disabled and not buttons[2].disabled, "only unlocked tables are clickable")
        buttons[6].dispatch("on_release")
        check(s.table is not None and s.table_number == 7, "table button starts a game at table 7")
        check(len(s.table.seats) == 4, "three opponents seated")
        view.refresh(force=True)
        check(len(view.opponents.children) == 4, "each opponent rendered (+ spacer)")

        # Mulligan through its button.
        dealt = list(s.table.seats[HUMAN].hand)
        view.btn_mulligan.dispatch("on_release")
        check(s.pending("Mulligan") == 0, "Mulligan button spends the mulligan")
        check(s.table.seats[HUMAN].hand.count(0) >= 1, "granted Bo card survives the mulligan")
        del dealt

        # Find a playable hand card, select it, and check the targets light up.
        t = s.table
        playable = [(i, b) for i, c in enumerate(t.seats[HUMAN].hand)
                    for b in range(4) if t.fits(c, b)]
        check(bool(playable), "something in hand is playable (the granted wild at least)")
        i, b = playable[0]
        view.refresh(force=True)
        hand_cards = [f.children[0] for f in reversed(view.hand.children) if f.children]
        hand_cards[i].dispatch("on_release")
        check(view.selected == ("hand", i), "clicking a hand card selects it")
        view.refresh(force=True)
        check(b in view._targets(t), "the build pile it fits is highlighted")
        size = len(t.seats[HUMAN].hand)
        build_cols = list(reversed(view.builds.children))[:4]
        build_cols[b].children[0].children[0].dispatch("on_release")
        check(len(s.table.seats[HUMAN].hand) in (size - 1, s.hand_size), "clicking the build pile plays it")
        check(view.btn_undo.disabled is False or s.table.refills, "undo is offered after a play")

        if s.can_undo:
            view.btn_undo.dispatch("on_release")
            check(len(s.table.seats[HUMAN].hand) == size, "Undo puts the card back")

        # Spare Wild button.
        before = s.table.seats[HUMAN].hand.count(0)
        view.btn_wild.dispatch("on_release")
        check(s.table.seats[HUMAN].hand.count(0) == before + 1, "Spare Wild adds a wild")

        # End the turn by selecting a card and clicking a discard pile.
        view.refresh(force=True)
        hand_cards = [f.children[0] for f in reversed(view.hand.children) if f.children]
        hand_cards[0].dispatch("on_release")
        mine = list(reversed(view.mine.children))
        discard_cols = mine[2:6]
        turns = s.table.turns
        discard_cols[0].children[0].children[0].dispatch("on_release")
        check(s.table.turns > turns, "clicking a discard pile ends the turn")
        check(s.game_over or s.table.current == HUMAN, "opponents played back round to you")
        view.refresh(force=True)
        check(len(ctx.feed) > 0, "the table log shows the opponents' moves")

        view.btn_hint.dispatch("on_release")
        view.btn_autostock.dispatch("on_release")
        check(s.auto_stock, "Auto-stock toggles on")

        view.refresh(force=True)
        Clock.schedule_once(lambda _d: Window.screenshot(name=OUT), 2.0)

        def finish(_d):
            view.btn_autogame.dispatch("on_release")
            check(s.game_over and s.last_result is not None, "Auto game finishes and settles")
            check(bool(ctx.pending_locations), f"checks queued: {len(ctx.pending_locations)}")
            ui.stop()

        Clock.schedule_once(finish, 3.5)

    Clock.schedule_once(exercise, 2.5)
    await ctx.ui_task
    ctx.exit_event.set()
    print()
    if failures:
        print(f"{len(failures)} UI check(s) FAILED")
        sys.exit(1)
    print("all UI checks passed")


asyncio.run(main())
