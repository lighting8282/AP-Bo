// The Skip-Bo table. A line-for-line port of skipbo/game/engine.py; the
// crosscheck test replays Python games through it and compares every event.
//
// A move source is ["hand", index], ["stock", 0] or ["discard", pile].

import { MAX_RANK, WILD, cardName, shuffledDeck } from "./cards.js?v=040ed05b";

export const BUILD_PILES = 4;
export const MAX_DISCARD_PILES = 4;
export const TURN_LIMIT = 600;

export const PLAYING = "playing";
export const WON = "won";
export const STALLED = "stalled";

export class Seat {
  constructor(name, stock = [], { handSize = 5, discardSlots = MAX_DISCARD_PILES } = {}) {
    this.name = name;
    this.stock = stock;
    this.handSize = handSize;
    this.discardSlots = discardSlots;
    this.hand = [];
    this.discards = Array.from({ length: MAX_DISCARD_PILES }, () => []);
    this.stockPlayed = 0;
    this.wildsPlayed = 0;
    this.pilesCompleted = 0;
    this.cardsPlayed = 0;
  }

  get stockTop() {
    return this.stock.length ? this.stock[this.stock.length - 1] : null;
  }

  discardTop(pile) {
    const stack = this.discards[pile];
    return stack.length ? stack[stack.length - 1] : null;
  }

  clone() {
    const copy = Object.assign(Object.create(Seat.prototype), this);
    copy.stock = [...this.stock];
    copy.hand = [...this.hand];
    copy.discards = this.discards.map((d) => [...d]);
    return copy;
  }
}

export class Table {
  constructor(seats, rng, deck = []) {
    this.seats = seats;
    this.rng = rng;
    this.drawPile = deck;
    this.builds = Array.from({ length: BUILD_PILES }, () => []);
    this.setAside = [];
    this.current = 0;
    this.turns = 0;
    this.state = PLAYING;
    this.winner = null;
    this.events = [];
    this.refills = 0;
  }

  static deal(rng, seats, stockSizes, { wilds = 18, bonusWilds = {} } = {}) {
    const deck = shuffledDeck(rng, wilds);
    seats.forEach((seat, i) => {
      seat.stock = [];
      for (let n = 0; n < stockSizes[i]; n += 1) seat.stock.push(deck.pop());
    });
    const table = new Table(seats, rng, deck);
    // Object key order is insertion order for these small integer keys,
    // which matches Python's dict iteration in Table.deal.
    for (const [index, extra] of Object.entries(bonusWilds)) {
      if (extra) {
        table.refill(seats[Number(index)]);
        for (let n = 0; n < extra; n += 1) seats[Number(index)].hand.push(WILD);
      }
    }
    table.startTurn();
    return table;
  }

  clone() {
    const copy = Object.assign(Object.create(Table.prototype), this);
    copy.seats = this.seats.map((s) => s.clone());
    copy.drawPile = [...this.drawPile];
    copy.builds = this.builds.map((b) => [...b]);
    copy.setAside = [...this.setAside];
    copy.events = [...this.events];
    return copy;
  }

  // -- queries -------------------------------------------------------------
  get seat() {
    return this.seats[this.current];
  }

  needed(build) {
    return this.builds[build].length + 1;
  }

  fits(card, build) {
    return card === WILD || card === this.needed(build);
  }

  sourceCard([kind, index]) {
    const seat = this.seat;
    if (kind === "hand") return index >= 0 && index < seat.hand.length ? seat.hand[index] : null;
    if (kind === "stock") return seat.stockTop;
    if (kind === "discard") {
      return index >= 0 && index < MAX_DISCARD_PILES ? seat.discardTop(index) : null;
    }
    throw new Error(`unknown source ${kind}`);
  }

  legalPlays() {
    if (this.state !== PLAYING) return [];
    const seat = this.seat;
    const sources = seat.stock.length ? [["stock", 0]] : [];
    seat.hand.forEach((_, i) => sources.push(["hand", i]));
    for (let p = 0; p < MAX_DISCARD_PILES; p += 1) {
      if (seat.discards[p].length) sources.push(["discard", p]);
    }
    const out = [];
    for (const src of sources) {
      for (let b = 0; b < BUILD_PILES; b += 1) {
        if (this.fits(this.sourceCard(src), b)) out.push([src, b]);
      }
    }
    return out;
  }

  canDiscardTo(pile) {
    return pile >= 0 && pile < this.seat.discardSlots;
  }

  // -- actions -------------------------------------------------------------
  play(source, build) {
    if (this.state !== PLAYING) throw new Error("The game is over.");
    if (!(build >= 0 && build < BUILD_PILES)) throw new Error(`There is no build pile ${build + 1}.`);
    const card = this.sourceCard(source);
    if (card === null) throw new Error("Nothing to play from there.");
    if (!this.fits(card, build)) {
      throw new Error(`Build pile ${build + 1} needs a ${this.needed(build)}, not a ${cardName(card)}.`);
    }

    const seat = this.seat;
    const [kind, index] = source;
    if (kind === "hand") seat.hand.splice(index, 1);
    else if (kind === "stock") seat.stock.pop();
    else seat.discards[index].pop();

    const value = this.needed(build);
    this.builds[build].push(card);
    seat.cardsPlayed += 1;
    if (card === WILD) seat.wildsPlayed += 1;
    const shown = card === WILD ? `W as ${value}` : String(value);
    const where = { hand: "hand", stock: "stockpile", discard: "a discard pile" }[kind];
    this.log(`plays ${shown} from ${where} onto build ${build + 1}`);

    if (value === MAX_RANK) {
      this.setAside.push(...this.builds[build]);
      this.builds[build] = [];
      seat.pilesCompleted += 1;
      this.log(`completes build pile ${build + 1}`);
    }

    if (kind === "stock") {
      seat.stockPlayed += 1;
      if (!seat.stock.length) {
        this.state = WON;
        this.winner = this.current;
        this.log("plays the last stockpile card. Game over!");
        return card;
      }
    }

    if (!seat.hand.length) this.refill(seat);
    return card;
  }

  discard(handIndex, pile) {
    if (this.state !== PLAYING) throw new Error("The game is over.");
    const seat = this.seat;
    if (!(handIndex >= 0 && handIndex < seat.hand.length)) throw new Error("No such card in hand.");
    if (!this.canDiscardTo(pile)) throw new Error(`Discard pile ${pile + 1} is locked.`);
    const [card] = seat.hand.splice(handIndex, 1);
    seat.discards[pile].push(card);
    this.log(`discards ${cardName(card)} to pile ${pile + 1}`);
    this.endTurn();
    return card;
  }

  passTurn() {
    if (this.seat.hand.length) throw new Error("You must discard to end your turn.");
    this.log("has nothing to discard and passes");
    this.endTurn();
  }

  // -- internals -----------------------------------------------------------
  endTurn() {
    this.turns += 1;
    if (this.turns >= TURN_LIMIT) {
      this.state = STALLED;
      this.log("-- the game is called: nobody can finish");
      return;
    }
    this.current = (this.current + 1) % this.seats.length;
    this.startTurn();
  }

  startTurn() {
    this.refill(this.seat);
    if (!this.drawPile.length && !this.setAside.length && !this.seats.some((s) => s.hand.length)) {
      this.state = STALLED;
    }
  }

  refill(seat) {
    while (seat.hand.length < seat.handSize) {
      if (!this.drawPile.length) {
        if (!this.setAside.length) break;
        this.drawPile = this.setAside;
        this.setAside = [];
        this.rng.shuffle(this.drawPile);
        this.events.push({ seat: -1, text: "Finished piles are shuffled back into the deck." });
      }
      seat.hand.push(this.drawPile.pop());
    }
    this.refills += 1;
  }

  log(text) {
    this.events.push({ seat: this.current, text });
  }
}
