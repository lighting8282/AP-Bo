"""A Skip-Bo tab for the Archipelago client window.

Play is click-to-select, click-to-place: pick a source (a hand card, your
stockpile, or a discard pile's top), and the build piles it fits light up;
click one to play, or click one of your discard piles to discard a hand card
and end the turn. Clicking a selected card again plays it to the first build
pile it fits. Everything still runs through the typed commands, so the
buttons and the console cannot disagree.

Keyboard (when the command line is not focused): 1-7 select a hand card,
S the stockpile, H hint, U undo, A auto-turn, Esc clear the selection.
"""

from __future__ import annotations

from importlib import resources
from io import BytesIO
from typing import TYPE_CHECKING

# kvui MUST be imported before anything from kivy. Keep this order.
from kvui import GameManager

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.layout import Layout
from kivy.uix.widget import Widget

from ..data import GAME_NAME, MULLIGAN, STORE_PRICES, SPARE_WILD, STOCK_SHRINK, TABLE_COUNT, TIERS
from ..game.cards import WILD, card_filename, card_name
from ..game.engine import BUILD_PILES, MAX_DISCARD_PILES, State
from ..game.tables import TABLES
from .session import HUMAN

if TYPE_CHECKING:
    from .context import SkipBoContext

CARD_H = 104
CARD_W = CARD_H * 2 // 3
SMALL_H = 60
SMALL_W = SMALL_H * 2 // 3

SELECTED = (1.0, 0.85, 0.25, 1)
TARGET = (0.30, 0.85, 0.45, 1)
NEUTRAL = (0.16, 0.16, 0.19, 1)
LOCKED = (0.35, 0.12, 0.12, 1)

_textures: dict[str, object] = {}


def texture_for(filename: str):
    """Card art, loaded once. Read via importlib.resources so it works from
    inside a zipped .apworld as well as a source folder."""
    if filename not in _textures:
        try:
            data = (resources.files(__package__).joinpath("assets").joinpath("cards")
                    .joinpath(filename).read_bytes())
            _textures[filename] = CoreImage(BytesIO(data), ext="png").texture
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            _textures[filename] = None
    return _textures[filename]


class Framed(BoxLayout):
    """A box with a coloured backdrop, used as the highlight around a card."""

    def __init__(self, color=NEUTRAL, **kwargs) -> None:
        super().__init__(padding=3, **kwargs)
        with self.canvas.before:
            self._color = Color(*color)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._rect, "pos", self.pos),
                  size=lambda *_: setattr(self._rect, "size", self.size))

    def set_color(self, color) -> None:
        self._color.rgba = color


class CardImage(ButtonBehavior, Image):
    pass


def card_widget(card, on_press=None, face_down: bool = False, text: str = "", **kwargs):
    """A card face (or back, or an empty-pile placeholder with `text`)."""
    tex = texture_for("back.png" if face_down else card_filename(card)) if (
        card is not None or face_down) else None
    if tex is not None:
        w = CardImage(fit_mode="contain", **kwargs)
        w.texture = tex
    else:
        label = text or (card_name(card) if card is not None else "")
        w = Button(text=label, background_normal="", background_color=(0.24, 0.24, 0.28, 1),
                   font_size="13sp", halign="center", **kwargs)
        w.bind(size=lambda b, _: setattr(b, "text_size", b.size))
        w.valign = "middle"
    if on_press is not None:
        w.bind(on_release=lambda _w: on_press())
    return w


def caption(text: str, height: int = 18, size: str = "12sp") -> Label:
    lab = Label(text=text, markup=True, size_hint_y=None, height=height, font_size=size)
    return lab


class SkipBoView(BoxLayout):
    def __init__(self, manager: "SkipBoManager", **kwargs) -> None:
        super().__init__(orientation="horizontal", padding=6, spacing=8, **kwargs)
        self.manager = manager
        self.selected: tuple[str, int] | None = None
        self.hint_text = ""
        self._signature = None

        left = BoxLayout(orientation="vertical", spacing=4)
        self.header = Label(markup=True, size_hint_y=None, height=24, halign="left",
                            valign="middle", font_size="15sp")
        self.subheader = Label(markup=True, size_hint_y=None, height=20, halign="left",
                               valign="middle", font_size="13sp")
        for lab in (self.header, self.subheader):
            lab.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        self.opponents = BoxLayout(size_hint_y=None, height=SMALL_H + 22, spacing=10)
        self.builds = BoxLayout(size_hint_y=None, height=CARD_H + 26, spacing=8)
        self.mine = BoxLayout(size_hint_y=None, height=CARD_H + 26, spacing=8)
        self.hand = BoxLayout(size_hint_y=None, height=CARD_H + 8, spacing=4)
        self.status = Label(markup=True, size_hint_y=None, height=22, halign="left",
                            valign="middle", font_size="14sp")
        self.status.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        self.actions = BoxLayout(size_hint_y=None, height=36, spacing=4)
        self.tables = GridLayout(cols=TABLE_COUNT, spacing=3, size_hint_y=None, height=46)
        self.store = BoxLayout(size_hint_y=None, height=0, spacing=3)
        for w in (self.header, self.subheader, self.opponents,
                  caption("[b]Build piles[/b]"), self.builds,
                  caption("[b]Your stockpile and discard piles[/b]"), self.mine,
                  caption("[b]Your hand[/b] -- click to select, click again to auto-place"),
                  self.hand, self.status, self.actions,
                  caption("[b]Tables[/b] -- click to sit down   (P pile  W won  D dominant)"),
                  self.tables, self.store, Widget()):
            left.add_widget(w)

        right = BoxLayout(orientation="vertical", size_hint_x=None, width=300, spacing=2)
        right.add_widget(caption("[b]Table log[/b]", 20, "13sp"))
        self.feed = Label(markup=False, halign="left", valign="top", font_size="12sp")
        self.feed.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        right.add_widget(self.feed)

        self.add_widget(left)
        self.add_widget(right)
        self._build_actions()
        Window.bind(on_key_down=self._on_key)

    # -- input -------------------------------------------------------------
    @property
    def session(self):
        return self.manager.ctx.session

    def run(self, command: str) -> None:
        self.hint_text = ""
        self.manager.commandprocessor(command)
        self.refresh(force=True)

    def _build_actions(self) -> None:
        self.toggle_button = None
        for label, command in (("Hint [H]", "/hint"), ("Undo [U]", "/undo"),
                               ("Auto turn [A]", "/auto"), ("Auto game", "/autogame"),
                               ("Mulligan", "/mulligan"), ("Spare Wild", "/wild"),
                               ("Auto-stock", "/autostock"), ("Forfeit", "/forfeit")):
            b = Button(text=label, font_size="13sp")
            b.bind(on_release=lambda _w, c=command: self._action(c))
            self.actions.add_widget(b)
            if command == "/autostock":
                self.toggle_button = b
            setattr(self, f"btn_{command[1:]}", b)

    def _action(self, command: str) -> None:
        self.selected = None
        self.hint_text = ""
        if command == "/hint":
            # Shown in the tab, not just the console: that is where you are looking.
            try:
                self.hint_text = self.session.hint()
            except RuntimeError as e:
                self.hint_text = str(e)
            self.refresh(force=True)
            return
        self.run(command)

    def _on_key(self, _window, key, _scancode, codepoint, modifiers) -> bool:
        ti = getattr(self.manager, "textinput", None)
        if ti is not None and ti.focus:
            return False
        tab = getattr(getattr(self.manager, "screens", None), "current_tab", None)
        if tab is None or tab.content is not self:
            return False  # another tab is showing
        if key == 27:
            self.selected = None
            self.refresh(force=True)
            return True
        c = (codepoint or "").lower()
        if c.isdigit() and c != "0":
            self.select(("hand", int(c) - 1))
        elif c == "s":
            self.select(("stock", 0))
        elif c == "h":
            self._action("/hint")
        elif c == "u" or (c == "z" and "ctrl" in modifiers):
            self._action("/undo")
        elif c == "a":
            self._action("/auto")
        else:
            return False
        return True

    def select(self, source: tuple[str, int]) -> None:
        s = self.session
        if not s.my_turn:
            return
        table = s.table
        if table.source_card(source) is None:
            return
        if self.selected == source:
            # Second click: place it on the first pile it fits.
            card = table.source_card(source)
            fits = [b for b in range(BUILD_PILES) if table.fits(card, b)]
            self.selected = None
            if fits:
                self.run(f"/p {self._src_text(source)} {fits[0] + 1}")
            else:
                self.refresh(force=True)
            return
        self.selected = source
        self.refresh(force=True)

    @staticmethod
    def _src_text(source) -> str:
        kind, i = source
        return "s" if kind == "stock" else f"{kind[0]}{i + 1}"

    def click_build(self, build: int) -> None:
        if self.selected is None:
            return
        source, self.selected = self.selected, None
        self.run(f"/p {self._src_text(source)} {build + 1}")

    def click_discard(self, pile: int) -> None:
        if self.selected and self.selected[0] == "hand":
            source, self.selected = self.selected, None
            self.run(f"/discard {source[1] + 1} {pile + 1}")
        else:
            self.select(("discard", pile))

    # -- rendering ---------------------------------------------------------
    def signature(self):
        s = self.session
        t = s.table
        board = None
        if t is not None:
            board = (t.state, t.current, tuple(map(tuple, t.builds)),
                     tuple((tuple(x.stock[-1:]), len(x.stock), tuple(x.hand),
                            tuple(map(tuple, x.discards))) for x in t.seats), len(t.events))
        return (board, self.selected, self.hint_text, s.auto_stock, tuple(sorted(s.counts.items())),
                s.stats.games_played, tuple(sorted(s.stats.bought)), s.can_undo,
                len(self.manager.ctx.feed), s.game_id)

    def refresh(self, force: bool = False) -> None:
        self.manager.ctx.report_events(quiet=True)
        sig = self.signature()
        if not force and sig == self._signature:
            return
        self._signature = sig
        s = self.session
        t = s.table
        if t is not None and self.selected is not None and (
                not s.my_turn or t.source_card(self.selected) is None):
            self.selected = None

        self.header.text = (
            f"[b]{s.goal_text}[/b]    won {s.stats.games_won}/{s.stats.games_played} games    "
            f"stockpile cards {s.stats.stock_played}    build piles {s.stats.piles}")
        items = (f"discard piles [b]{s.discard_piles}[/b]   hand [b]{s.hand_size}[/b]   "
                 f"Skip-Bo cards [b]{s.bonus_wilds}[/b]   shrinks [b]{s.count(STOCK_SHRINK)}[/b]"
                 f"   power {s.power}")
        consumables = f"   mulligans {s.pending(MULLIGAN)}   spare wilds {s.pending(SPARE_WILD)}"
        self.subheader.text = items + consumables
        self.toggle_button.text = f"Auto-stock: {'ON' if s.auto_stock else 'off'}"
        self.btn_undo.disabled = not s.can_undo
        self.btn_mulligan.disabled = not (s.my_turn and s.mulligan_open and s.pending(MULLIGAN))
        self.btn_wild.disabled = not (s.my_turn and s.pending(SPARE_WILD))
        for name in ("hint", "auto", "autogame", "forfeit"):
            getattr(self, f"btn_{name}").disabled = not (
                s.my_turn if name != "forfeit" else (t is not None and t.state is State.PLAYING))

        self._render_opponents(t)
        self._render_builds(t)
        self._render_mine(t)
        self._render_hand(t)
        self._render_status(s, t)
        self._render_tables(s)
        self._render_store(s)
        self.feed.text = "\n".join(self.manager.ctx.feed[-40:])

    def _render_opponents(self, t) -> None:
        self.opponents.clear_widgets()
        if t is None:
            return
        for i, seat in enumerate(t.seats[1:], 1):
            box = BoxLayout(orientation="vertical", size_hint_x=None,
                            width=SMALL_W * 5 + 24)
            turn = "  [color=ffd479]<- playing[/color]" if t.current == i and t.state is State.PLAYING else ""
            box.add_widget(caption(f"[b]{seat.name}[/b] stock {len(seat.stock)}  "
                                   f"hand {len(seat.hand)}{turn}", 18, "12sp"))
            row = BoxLayout(spacing=3)
            f = Framed(SELECTED if t.current == i else NEUTRAL, size_hint_x=None, width=SMALL_W + 6)
            f.add_widget(card_widget(seat.stock_top, text="out"))
            row.add_widget(f)
            row.add_widget(Widget(size_hint_x=None, width=6))
            for p in range(MAX_DISCARD_PILES):
                top = seat.discard_top(p)
                row.add_widget(card_widget(top, text="", size_hint_x=None, width=SMALL_W))
            box.add_widget(row)
            self.opponents.add_widget(box)
        self.opponents.add_widget(Widget())

    def _targets(self, t) -> set[int]:
        if t is None or self.selected is None:
            return set()
        card = t.source_card(self.selected)
        if card is None:
            return set()
        return {b for b in range(BUILD_PILES) if t.fits(card, b)}

    def _render_builds(self, t) -> None:
        self.builds.clear_widgets()
        targets = self._targets(t)
        for b in range(BUILD_PILES):
            col = BoxLayout(orientation="vertical", size_hint_x=None, width=CARD_W + 30)
            if t is None:
                col.add_widget(caption(f"Build {b + 1}"))
                col.add_widget(card_widget(None, text="--"))
                self.builds.add_widget(col)
                continue
            pile = t.builds[b]
            top = pile[-1] if pile else None
            col.add_widget(caption(f"#{b + 1}  needs [b]{t.needed(b)}[/b]  ({len(pile)})"))
            frame = Framed(TARGET if b in targets else NEUTRAL)
            label = f"empty\nneeds 1"
            w = card_widget(top, on_press=lambda b=b: self.click_build(b), text=label)
            frame.add_widget(w)
            col.add_widget(frame)
            self.builds.add_widget(col)
        info = Label(markup=True, halign="left", valign="middle", font_size="12sp")
        info.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        if t is not None:
            info.text = (f"draw pile {len(t.draw_pile)}\nset aside {len(t.set_aside)}\n"
                         f"turn {t.turns + 1}")
        self.builds.add_widget(info)

    def _render_mine(self, t) -> None:
        self.mine.clear_widgets()
        if t is None:
            self.mine.add_widget(Label(text="No game in progress -- pick a table below."))
            return
        me = t.seats[HUMAN]
        col = BoxLayout(orientation="vertical", size_hint_x=None, width=CARD_W + 30)
        col.add_widget(caption(f"[b]Stockpile[/b] ({len(me.stock)})"))
        frame = Framed(SELECTED if self.selected == ("stock", 0) else (0.45, 0.3, 0.1, 1))
        frame.add_widget(card_widget(me.stock_top, on_press=lambda: self.select(("stock", 0)),
                                     text="empty"))
        col.add_widget(frame)
        self.mine.add_widget(col)
        self.mine.add_widget(Widget(size_hint_x=None, width=14))

        hand_selected = self.selected is not None and self.selected[0] == "hand"
        for p in range(MAX_DISCARD_PILES):
            stack = me.discards[p]
            col = BoxLayout(orientation="vertical", size_hint_x=None, width=CARD_W + 30)
            locked = p >= me.discard_slots
            under = " ".join(card_name(c) for c in stack[-5:-1])
            col.add_widget(caption(
                "[color=aa6666]locked[/color]" if locked
                else f"Discard {p + 1}" + (f" [size=10sp]{under}[/size]" if under else "")))
            if locked:
                color = LOCKED
            elif self.selected == ("discard", p):
                color = SELECTED
            elif hand_selected and t.current == HUMAN:
                color = (0.25, 0.45, 0.75, 1)   # a valid place to end the turn
            else:
                color = NEUTRAL
            frame = Framed(color)
            frame.add_widget(card_widget(
                stack[-1] if stack else None,
                on_press=None if locked else (lambda p=p: self.click_discard(p)),
                text="locked" if locked else "empty"))
            col.add_widget(frame)
            self.mine.add_widget(col)
        self.mine.add_widget(Widget())

    def _render_hand(self, t) -> None:
        self.hand.clear_widgets()
        if t is None:
            return
        me = t.seats[HUMAN]
        playable = {i for i, c in enumerate(me.hand)
                    if any(t.fits(c, b) for b in range(BUILD_PILES))}
        for i, card in enumerate(me.hand):
            if self.selected == ("hand", i):
                color = SELECTED
            elif i in playable and s_turn(t):
                color = (0.22, 0.42, 0.28, 1)  # this card fits somewhere
            else:
                color = NEUTRAL
            frame = Framed(color, size_hint_x=None, width=CARD_W + 6)
            frame.add_widget(card_widget(card, on_press=lambda i=i: self.select(("hand", i))))
            self.hand.add_widget(frame)
        self.hand.add_widget(Widget())

    def _render_status(self, s, t) -> None:
        if self.hint_text and s.my_turn and self.selected is None:
            self.status.text = f"[color=ffd479]Hint:[/color] {self.hint_text}"
        elif t is None:
            self.status.text = "Choose a table to start."
        elif t.state is State.WON:
            who = t.seats[t.winner].name
            self.status.text = (f"[color=88ee88][b]You win![/b][/color]  Pick a table to play again."
                                if t.winner == HUMAN else
                                f"[color=ff8888][b]{who} wins.[/b][/color]  Pick a table to play again.")
        elif t.state is State.STALLED:
            self.status.text = "[color=ff8888]Game over -- nobody won.[/color]  Pick a table."
        elif not s.my_turn:
            self.status.text = "Opponents are playing..."
        elif self.selected is None:
            self.status.text = ("[b]Your turn.[/b] Select a card to play; end the turn by "
                                "selecting a hand card and clicking a discard pile.")
        else:
            card = t.source_card(self.selected)
            where = "a discard pile to discard it, or " if self.selected[0] == "hand" else ""
            self.status.text = (f"Selected [b]{card_name(card)}[/b] -- click a green build pile, "
                                f"{where}Esc to cancel.")

    def _render_tables(self, s) -> None:
        self.tables.clear_widgets()
        st = s.stats
        for n, spec in TABLES.items():
            marks = []
            for tier, have in zip(TIERS, (st.tables_piled, st.tables_won, st.tables_dominant)):
                if tier in s.tiers:
                    marks.append(tier[0] if n in have else "-")
            b = Button(text=f"{n}\n{''.join(marks)}", font_size="12sp", halign="center",
                       background_normal="")
            if n in st.tables_won:
                b.background_color = (0.18, 0.55, 0.30, 1)
            elif n in s.unlocked_tables:
                b.background_color = (0.25, 0.45, 0.75, 1)
            else:
                b.background_color = (0.30, 0.30, 0.34, 1)
                b.disabled = True
            b.bind(on_release=lambda _w, n=n: self._action(f"/play {n}"))
            self.tables.add_widget(b)

    def _render_store(self, s) -> None:
        self.store.clear_widgets()
        if not s.store_slots:
            self.store.height = 0
            return
        self.store.height = 32
        self.store.add_widget(Label(text=f"Store: {s.points_left} pts", size_hint_x=None,
                                    width=110, font_size="12sp"))
        for slot in range(1, s.store_slots + 1):
            bought = slot in s.stats.bought
            refusal = None if bought else s.can_buy(slot)
            b = Button(text="bought" if bought else
                       f"Slot {slot}  ({STORE_PRICES[slot - 1]} pt)",
                       font_size="12sp", disabled=bought or refusal is not None)
            b.bind(on_release=lambda _w, n=slot: self._action(f"/buy {n}"))
            self.store.add_widget(b)


def s_turn(t) -> bool:
    return t.state is State.PLAYING and t.current == HUMAN


class SkipBoManager(GameManager):
    base_title = f"Archipelago {GAME_NAME} Client"
    ctx: "SkipBoContext"

    def build(self) -> Layout:
        container = super().build()
        self.game_view = SkipBoView(self)
        self.game_tab = self.add_client_tab("Skip-Bo", self.game_view)
        Clock.schedule_interval(lambda _dt: self.game_view.refresh(), 1 / 4)
        return container
