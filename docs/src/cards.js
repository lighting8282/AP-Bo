// Card model. Mirrors apbo/game/cards.py: a card is a number, 1-12, or
// WILD (0). Careful: WILD is falsy, so test for null, never for truthiness.

export const WILD = 0;
export const MIN_RANK = 1;
export const MAX_RANK = 12;
export const COPIES_PER_RANK = 12;
export const STOCK_WILDS = 18;

export function buildDeck(wilds = STOCK_WILDS) {
  const deck = [];
  for (let rank = MIN_RANK; rank <= MAX_RANK; rank += 1) {
    for (let i = 0; i < COPIES_PER_RANK; i += 1) deck.push(rank);
  }
  for (let i = 0; i < wilds; i += 1) deck.push(WILD);
  return deck;
}

export function shuffledDeck(rng, wilds = STOCK_WILDS) {
  const deck = buildDeck(wilds);
  rng.shuffle(deck);
  return deck;
}

export const cardName = (card) => (card === null || card === undefined ? "--"
  : card === WILD ? "W" : String(card));

export const cardFile = (card) => (card === WILD ? "wild.png"
  : `card_${String(card).padStart(2, "0")}.png`);
