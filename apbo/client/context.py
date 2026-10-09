"""Archipelago client for AP_Bo.

Every action is a command, and the GUI tab only ever calls commands, so typed
play and clicked play are the same code path. Commands are synchronous while
sending is async: checks are queued here and drained by bo_loop.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from CommonClient import ClientCommandProcessor, CommonContext, logger, server_loop
from NetUtils import ClientStatus

from ..data import GAME_NAME, MULLIGAN, SPARE_WILD, STORE_PRICES, TABLE_COUNT, store_gate
from ..game.cards import card_name
from ..game.engine import BUILD_PILES, State
from ..game.tables import TABLES
from .session import HUMAN, BoSession


def parse_source(text: str):
    """h3 = hand card 3, s = stockpile, d2 = discard pile 2 (all 1-based)."""
    text = text.lower().strip()
    if text in ("s", "stock"):
        return ("stock", 0)
    if text[:1] in ("h", "d") and text[1:].isdigit():
        return ("hand" if text[0] == "h" else "discard", int(text[1:]) - 1)
    raise ValueError(f"'{text}' is not a source -- use h1..h7, s, or d1..d4")


def describe_table(session: BoSession) -> list[str]:
    t = session.table
    lines = []
    builds = "  ".join(
        f"[{b + 1}] {card_name(t.builds[b][-1]) if t.builds[b] else '--'}"
        f"(needs {t.needed(b)})" for b in range(BUILD_PILES))
    lines.append(f"build piles: {builds}")
    for i, seat in enumerate(t.seats):
        piles = " ".join(
            ("x" if p >= seat.discard_slots else card_name(seat.discard_top(p)))
            for p in range(4))
        who = ">" if i == t.current and t.state is State.PLAYING else " "
        lines.append(f"{who}{seat.name:<6} stock {card_name(seat.stock_top)} "
                     f"({len(seat.stock)} left)  discards {piles}")
    me = t.seats[HUMAN]
    hand = "  ".join(f"h{i + 1}:{card_name(c)}" for i, c in enumerate(me.hand))
    lines.append(f"your hand: {hand}")
    return lines


class BoCommandProcessor(ClientCommandProcessor):
    ctx: BoContext

    def _try(self, fn, *args) -> bool:
        try:
            fn(*args)
        except (RuntimeError, ValueError) as e:
            self.output(str(e))
            return False
        finally:
            self.ctx.after_action()
        return True

    def _cmd_tables(self) -> None:
        """List the tables and what you have done at each."""
        s = self.ctx.session
        for n, spec in TABLES.items():
            if n in s.stats.tables_won:
                mark = "won "
            elif n in s.unlocked_tables:
                mark = "open"
            else:
                mark = " -- "
            self.output(f"  {mark}  Table {n:>2}: {spec.description}")

    def _cmd_play(self, table: str) -> None:
        """Sit down at a table. Usage: /play 3"""
        try:
            number = int(table)
        except ValueError:
            self.output(f"Give a table number from 1 to {TABLE_COUNT}.")
            return
        if self._try(self.ctx.session.start, number):
            s = self.ctx.session
            self.output(f"Table {number}: {TABLES[number].description}")
            for note in s.trap_notes:
                self.output(f"TRAP -- {note}")
            self._cmd_show()

    def _cmd_show(self) -> None:
        """Show the build piles, every stockpile and discard pile, and your hand."""
        if self.ctx.session.table is None:
            self.output("No game yet. /tables, then /play <n>.")
            return
        for line in describe_table(self.ctx.session):
            self.output(line)

    def _cmd_p(self, source: str, build: str) -> None:
        """Play onto a build pile. Usage: /p h2 3  (s = stockpile, d1 = discard 1)"""
        try:
            src, b = parse_source(source), int(build) - 1
        except ValueError as e:
            self.output(str(e))
            return
        if self._try(self.ctx.session.play, src, b):
            self._cmd_show()

    def _cmd_discard(self, hand: str, pile: str) -> None:
        """Discard a hand card to end your turn. Usage: /discard 4 1"""
        try:
            h, p = int(hand) - 1, int(pile) - 1
        except ValueError:
            self.output("Usage: /discard <hand position> <pile>")
            return
        if self._try(self.ctx.session.discard, h, p):
            self.ctx.report_events()
            if not self.ctx.session.game_over:
                self._cmd_show()

    def _cmd_undo(self) -> None:
        """Take back your last play (never across a fresh draw)."""
        if self._try(self.ctx.session.undo):
            self._cmd_show()

    def _cmd_hint(self) -> None:
        """Suggest a move."""
        try:
            self.output(self.ctx.session.hint())
        except RuntimeError as e:
            self.output(str(e))

    def _cmd_auto(self) -> None:
        """Let the computer play your current turn."""
        if self._try(self.ctx.session.auto_turn):
            self.ctx.report_events()
            if not self.ctx.session.game_over:
                self._cmd_show()

    def _cmd_autogame(self) -> None:
        """Let the computer play the rest of the game for you."""
        if self._try(self.ctx.session.auto_game):
            self.ctx.report_events(quiet=True)

    def _cmd_autostock(self) -> None:
        """Toggle playing your stockpile card automatically when it fits."""
        s = self.ctx.session
        s.auto_stock = not s.auto_stock
        self.output(f"Auto-play stockpile: {'on' if s.auto_stock else 'off'}")

    def _cmd_mulligan(self) -> None:
        """Spend a Mulligan: redraw your opening hand."""
        if self._try(self.ctx.session.mulligan):
            self._cmd_show()

    def _cmd_wild(self) -> None:
        """Spend a Spare Wild: add a wild to your hand right now."""
        if self._try(self.ctx.session.spare_wild):
            self._cmd_show()

    def _cmd_forfeit(self) -> None:
        """Give up the current game (counts as a loss)."""
        self._try(self.ctx.session.forfeit)

    def _cmd_status(self) -> None:
        """Your items, consumables and progress."""
        s = self.ctx.session
        self.output(s.goal_text)
        self.output(f"discard piles {s.discard_piles} | hand size {s.hand_size} | "
                    f"Bo cards {s.bonus_wilds} | stockpile shrinks {s.count('Stockpile Shrink')}")
        self.output(f"mulligans {s.pending(MULLIGAN)} | spare wilds {s.pending(SPARE_WILD)}")
        st = s.stats
        self.output(f"games {st.games_played} played, {st.games_won} won | "
                    f"stockpile cards {st.stock_played} | build piles {st.piles}")

    def _cmd_store(self) -> None:
        """List the store slots."""
        s = self.ctx.session
        if not s.store_slots:
            self.output("This seed has no store.")
            return
        self.output(f"AP Points: {s.points_left} unspent of {s.points} received")
        for slot in range(1, s.store_slots + 1):
            refusal = None if slot in s.stats.bought else s.can_buy(slot)
            mark = "done" if slot in s.stats.bought else ("  --" if refusal else " buy")
            self.output(f"  {mark}  Slot {slot}: {STORE_PRICES[slot - 1]} pt(s), "
                        f"opens at {store_gate(slot)}" + (f"  ({refusal})" if refusal else ""))

    def _cmd_buy(self, slot: str) -> None:
        """Buy a store slot. Usage: /buy 2"""
        try:
            n = int(slot)
        except ValueError:
            self.output("Usage: /buy <slot>")
            return
        if self._try(self.ctx.session.buy, n):
            self.output(f"Bought slot {n}.")


class BoContext(CommonContext):
    game = GAME_NAME
    items_handling = 0b111
    command_processor = BoCommandProcessor

    def __init__(self, server_address: str | None = None, password: str | None = None) -> None:
        super().__init__(server_address, password)
        self.session = BoSession(rng=random.Random())
        self.pending_locations: list[int] = []
        self.goal_sent = False
        self.restore_state = "needed"
        self.save_pending = False
        self.death_link_pending = False
        self.tags_pending = False
        self._event_cursor = 0
        self.session_ready = False
        self._event_game = -1
        #: The GUI's own feed of table events; it reads and trims this.
        self.feed: list[str] = []

    @property
    def save_key(self) -> str:
        return f"apbo_game_{self.team}_{self.slot}"

    async def disconnect(self, *args, **kwargs) -> None:
        self.session_ready = False
        await super().disconnect(*args, **kwargs)

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect(game=self.game)

    def on_package(self, cmd: str, args: dict[str, Any]) -> None:
        if cmd == "Connected":
            self.session = BoSession(args.get("slot_data", {}), random.Random())
            self.session.reported = set(self.checked_locations)
            self.goal_sent = False
            self.restore_state = "needed"
            self.tags_pending = self.session.death_link
            self.session_ready = True
            self.sync_items()
            logger.info("Connected. /tables to see where you can sit, /play <n> to start.")
        elif cmd == "ReceivedItems":
            self.sync_items()
        elif cmd == "Retrieved":
            from .session import Stats
            keys = args.get("keys", {})
            if self.save_key not in keys:
                return  # someone else's Get (CommonClient asks for its own keys)
            payload = keys[self.save_key]
            stats = Stats.from_payload(payload)
            if stats is not None:
                self.session.stats = stats
                logger.info(f"Restored {stats.games_played} game(s), {stats.games_won} won.")
            self.restore_state = "done"
            self.after_action()

    def sync_items(self) -> None:
        names = [self.item_names.lookup_in_game(i.item, self.game) for i in self.items_received]
        before = self.session.unlocked_tables
        self.session.set_items(names)
        for t in sorted(self.session.unlocked_tables - before):
            logger.info(f"Table {t} unlocked: {TABLES[t].description}")

    def report_events(self, quiet: bool = False) -> None:
        """Read out what happened at the table since anyone last looked."""
        table = self.session.table
        if table is None:
            return
        if self.session.game_id != self._event_game:
            self._event_game, self._event_cursor = self.session.game_id, 0
        # An undo swaps in an older copy of the table whose log is shorter.
        self._event_cursor = min(self._event_cursor, len(table.events))
        fresh = table.events[self._event_cursor:]
        self._event_cursor = len(table.events)
        for e in fresh:
            if e.seat == HUMAN:
                verb, _, rest = e.text.partition(" ")
                line = f"You {verb[:-1] if verb.endswith('s') else verb} {rest}".rstrip()
            else:
                who = "" if e.seat < 0 else table.seats[e.seat].name + " "
                line = f"{who}{e.text}"
            self.feed.append(line)
            if not quiet and e.seat != HUMAN:
                logger.info(line)
        del self.feed[:-200]

    def after_action(self) -> None:
        """Bank a finished game and queue whatever checks are now earned."""
        s = self.session
        if s.game_over and s.last_result is None:
            self.report_events(quiet=True)
            result = s.settle()
            logger.info(str(result))
            self.save_pending = True
            if not result.won and s.death_link and not getattr(self, "_killed", False):
                self.death_link_pending = True
            self._killed = False
        if self.restore_state != "done":
            return  # stats are not trustworthy until the restore lands
        new = s.new_checks()
        if new:
            self.pending_locations.extend(new)
            self.save_pending = True

    def on_deathlink(self, data: dict[str, Any]) -> None:
        super().on_deathlink(data)
        s = self.session
        if s.table is None or s.table.state is not State.PLAYING:
            logger.info("DeathLink: no game in progress, nothing to lose.")
            return
        self._killed = True
        s.forfeit()
        self.after_action()

    async def bo_loop(self) -> None:
        while not self.exit_event.is_set():
            # Authenticated, not merely connected: the server ignores a Get
            # sent before Connected, and the restore would then never land.
            connected = (self.server and not self.server.socket.closed
                         and self.slot is not None and self.session_ready)
            if connected and self.tags_pending:
                self.tags_pending = False
                await self.update_death_link(self.session.death_link)
            if connected and self.death_link_pending:
                self.death_link_pending = False
                await self.send_death(f"{self.player_names.get(self.slot, 'A player')} lost at AP Bo.")
            if connected and self.restore_state == "needed":
                self.restore_state = "requested"
                await self.send_msgs([{"cmd": "Get", "keys": [self.save_key]}])
            if connected and self.save_pending and self.restore_state == "done":
                self.save_pending = False
                await self.send_msgs([{
                    "cmd": "Set", "key": self.save_key, "default": {}, "want_reply": False,
                    "operations": [{"operation": "replace",
                                    "value": self.session.stats.to_payload()}],
                }])
            if connected and self.pending_locations:
                queued, self.pending_locations = self.pending_locations, []
                await self.check_locations(queued)
            if connected and self.session.goal_met and not self.goal_sent:
                await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                self.finished_game = True
                self.goal_sent = True
                logger.info("Goal complete!")
            await asyncio.sleep(0.1)

    def make_gui(self):
        from .game_manager import BoManager
        return BoManager


async def main(args) -> None:
    from CommonClient import gui_enabled

    ctx = BoContext(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    ctx.client_loop = asyncio.create_task(ctx.bo_loop(), name="bo loop")
    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()
    await ctx.exit_event.wait()
    await ctx.shutdown()
