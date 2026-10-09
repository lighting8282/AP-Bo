"""Card model for AP Bo.

A card is an int: 1-12 for the numbers, WILD (0) for the wild. Nothing else
about a card matters to the rules -- the number cards have no suit -- so a
dataclass would only add ceremony.

The stock deck is 162 cards: twelve copies of each number and eighteen wilds.
"""

from __future__ import annotations

import random

WILD = 0
MIN_RANK = 1
MAX_RANK = 12
COPIES_PER_RANK = 12
STOCK_WILDS = 18

Card = int


def build_deck(wilds: int = STOCK_WILDS) -> list[Card]:
    return [rank for rank in range(MIN_RANK, MAX_RANK + 1)
            for _ in range(COPIES_PER_RANK)] + [WILD] * wilds


def shuffled_deck(rng: random.Random, wilds: int = STOCK_WILDS) -> list[Card]:
    deck = build_deck(wilds)
    rng.shuffle(deck)
    return deck


def card_name(card: Card | None) -> str:
    if card is None:
        return "--"
    return "W" if card == WILD else str(card)


def card_filename(card: Card) -> str:
    """The face image for a card. The art is Phase 10's, recoloured by band:
    1-4 blue, 5-8 green, 9-12 red, the way the printed deck groups them."""
    return "wild.png" if card == WILD else f"card_{card:02d}.png"


def parse_card(text: str) -> Card:
    text = text.strip().upper()
    if text in ("W", "WILD", "BO"):
        return WILD
    value = int(text)
    if not MIN_RANK <= value <= MAX_RANK:
        raise ValueError(f"no card {text}")
    return value
