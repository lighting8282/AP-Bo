// Items in, a dealt table and earned location IDs out. A port of
// apbo/client/session.py, with the same save payload, so the desktop client
// and this page can take turns on one slot.

import {
  AP_POINT, BASE_DISCARD_PILES, BASE_HAND_SIZE, DISCARD_PILE, GAMES_WON_MILESTONES, HAND_SIZE,
  LOCATION_NAME_TO_ID, LOCKED_DISCARD, MIN_STOCK, MULLIGAN, PILES_MILESTONES, RIVAL_WILD,
  SHRINK_STEP, BO_CARD, SPARE_WILD, STACKED_STOCK, STACK_STEP, STOCK_PLAYED_MILESTONES,
  STOCK_SHRINK, STORE_PRICES, TABLES, TABLE_COUNT, TIERS, gamesWonName, pilesName,
  stockPlayedName, storeGate, storeLocationName, tableLocationName, tableUnlock,
} from "./data.js?v=e59d38d1";
import { WILD } from "./cards.js?v=e59d38d1";
import { autoplay, bestPlan, chooseDiscard, takeTurn } from "./ai.js?v=e59d38d1";
import { PLAYING, Seat, Table } from "./engine.js?v=e59d38d1";
import { Rng } from "./rng.js?v=e59d38d1";

export const PAYLOAD_VERSION = 1;
export const HUMAN = 0;
export const GOAL_TABLE_TEN = 0;
export const GOAL_ALL_TABLES = 1;
export const GOAL_GAMES_WON = 2;

const tableSet = (values) => new Set(values
  .filter((t) => Number.isInteger(t) && t >= 1 && t <= TABLE_COUNT));

export class Stats {
  constructor() {
    this.gamesPlayed = 0;
    this.gamesWon = 0;
    this.stockPlayed = 0;
    this.piles = 0;
    this.tablesWon = new Set();
    this.tablesDominant = new Set();
    this.tablesPiled = new Set();
    this.trapsUsed = {};
    this.fillersUsed = {};
    this.bought = new Set();
    this.history = [];
  }

  toPayload() {
    const sorted = (s) => [...s].sort((a, b) => a - b);
    return {
      version: PAYLOAD_VERSION,
      games_played: this.gamesPlayed,
      games_won: this.gamesWon,
      stock_played: this.stockPlayed,
      piles: this.piles,
      tables_won: sorted(this.tablesWon),
      tables_dominant: sorted(this.tablesDominant),
      tables_piled: sorted(this.tablesPiled),
      traps_used: { ...this.trapsUsed },
      fillers_used: { ...this.fillersUsed },
      bought: sorted(this.bought),
      history: this.history.slice(-50),
    };
  }

  /** null for anything malformed: a payload is untrusted. */
  static fromPayload(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) return null;
    if (data.version !== PAYLOAD_VERSION) return null;
    const stats = new Stats();
    const keys = ["games_played", "games_won", "stock_played", "piles"];
    const ints = keys.map((k) => data[k]);
    if (ints.some((v) => !Number.isInteger(v) || v < 0)) return null;
    [stats.gamesPlayed, stats.gamesWon, stats.stockPlayed, stats.piles] = ints;
    if (!Array.isArray(data.tables_won) || !Array.isArray(data.bought)) return null;
    const optional = ["tables_dominant", "tables_piled", "history"];
    if (optional.some((k) => data[k] !== undefined && !Array.isArray(data[k]))) return null;
    for (const k of ["traps_used", "fillers_used"]) {
      const v = data[k];
      if (!v || typeof v !== "object" || Array.isArray(v)) return null;
      if (Object.values(v).some((n) => !Number.isInteger(n))) return null;
    }
    stats.tablesWon = tableSet(data.tables_won);
    stats.tablesDominant = tableSet(data.tables_dominant ?? []);
    stats.tablesPiled = tableSet(data.tables_piled ?? []);
    stats.trapsUsed = { ...data.traps_used };
    stats.fillersUsed = { ...data.fillers_used };
    stats.bought = new Set(data.bought.filter(Number.isInteger));
    stats.history = (data.history ?? [])
      .filter((h) => h && typeof h === "object" && !Array.isArray(h)).slice(-50);
    return stats;
  }
}

export function resultText(r) {
  if (r.won) return `You won at Table ${r.table} in ${r.turns} turns${r.dominant ? " -- dominant!" : ""}`;
  if (r.winner) return `${r.winner} won Table ${r.table}; you had ${r.stockLeft} stockpile card(s) left`;
  return `Table ${r.table} was called with nobody out`;
}

export class BoSession {
  constructor(slotData = {}, rng = new Rng()) {
    this.goal = Number(slotData.goal ?? GOAL_TABLE_TEN);
    this.gamesToWin = Number(slotData.games_to_win ?? 10);
    this.tiers = TIERS.slice(0, Number(slotData.checks_per_table ?? 2));
    this.storeSlots = Number(slotData.store_slots ?? 0);
    this.deathLink = Boolean(slotData.death_link ?? 0);
    this.rng = rng;

    this.counts = {};
    this.stats = new Stats();
    this.table = null;
    this.tableNumber = null;
    this.levels = [];
    this.lastResult = null;
    this.reported = new Set();
    this.undoStack = [];
    this.mulliganOpen = false;
    this.autoStock = false;
    this.trapNotes = [];
    this.gameId = 0;
  }

  // -- items ---------------------------------------------------------------
  setItems(names) {
    const counts = {};
    for (const n of names) counts[n] = (counts[n] ?? 0) + 1;
    this.counts = counts;
  }

  count(name) { return this.counts[name] ?? 0; }

  get unlockedTables() {
    const out = new Set();
    for (let t = 1; t <= TABLE_COUNT; t += 1) if (this.count(tableUnlock(t))) out.add(t);
    return out;
  }

  get discardPiles() { return Math.min(4, BASE_DISCARD_PILES + this.count(DISCARD_PILE)); }

  get handSize() { return BASE_HAND_SIZE + Math.min(2, this.count(HAND_SIZE)); }

  get bonusWilds() { return Math.min(4, this.count(BO_CARD)); }

  stockSize(table) {
    return Math.max(MIN_STOCK, TABLES[table].stock - SHRINK_STEP * Math.min(3, this.count(STOCK_SHRINK)));
  }

  pending(name) {
    const used = (this.stats.trapsUsed[name] ?? 0) + (this.stats.fillersUsed[name] ?? 0);
    return Math.max(0, this.count(name) - used);
  }

  get power() {
    return [DISCARD_PILE, HAND_SIZE, BO_CARD, STOCK_SHRINK].reduce((a, n) => a + this.count(n), 0);
  }

  // -- store ---------------------------------------------------------------
  get points() { return this.count(AP_POINT); }

  get pointsLeft() {
    let spent = 0;
    for (const s of this.stats.bought) spent += STORE_PRICES[s - 1] ?? 0;
    return this.points - spent;
  }

  canBuy(slot) {
    if (!(slot >= 1 && slot <= this.storeSlots)) return `There is no store slot ${slot}.`;
    if (this.stats.bought.has(slot)) return "Already bought.";
    if (this.points < storeGate(slot)) return `Opens once you have received ${storeGate(slot)} AP Points.`;
    if (this.pointsLeft < STORE_PRICES[slot - 1]) {
      return `Costs ${STORE_PRICES[slot - 1]}; you have ${this.pointsLeft} unspent.`;
    }
    return null;
  }

  buy(slot) {
    const refusal = this.canBuy(slot);
    if (refusal) throw new Error(refusal);
    this.stats.bought.add(slot);
    return LOCATION_NAME_TO_ID[storeLocationName(slot)];
  }

  // -- a game --------------------------------------------------------------
  canPlay(table) {
    if (!TABLES[table]) return `Pick a table from 1 to ${TABLE_COUNT}.`;
    if (!this.unlockedTables.has(table)) return `Table ${table} is not unlocked yet.`;
    if (this.table && this.table.state === PLAYING) return "Finish (or forfeit) the current game first.";
    return null;
  }

  start(table) {
    const refusal = this.canPlay(table);
    if (refusal) throw new Error(refusal);
    const spec = TABLES[table];
    const notes = [];

    let stock = this.stockSize(table);
    if (this.pending(STACKED_STOCK)) {
      this.spendTrap(STACKED_STOCK);
      stock += STACK_STEP;
      notes.push(`Stacked Stockpile: +${STACK_STEP} cards on your stockpile`);
    }
    let slots = this.discardPiles;
    if (this.pending(LOCKED_DISCARD) && slots > 1) {
      this.spendTrap(LOCKED_DISCARD);
      slots -= 1;
      notes.push("Locked Discard: one of your discard piles is closed this game");
    }
    let rival = 0;
    if (this.pending(RIVAL_WILD)) {
      this.spendTrap(RIVAL_WILD);
      rival = 1;
      notes.push("Rival Wild: every opponent starts with a wild");
    }

    const seats = [new Seat("You", [], { handSize: this.handSize, discardSlots: slots })];
    spec.opponents.forEach((_, i) => seats.push(new Seat(`CPU ${i + 1}`)));
    const bonus = { [HUMAN]: this.bonusWilds };
    for (let i = 1; i < seats.length; i += 1) bonus[i] = rival;
    this.table = Table.deal(this.rng, seats, [stock, ...spec.opponents.map(() => spec.stock)],
      { bonusWilds: bonus });
    this.tableNumber = table;
    this.gameId += 1;
    this.levels = ["hard", ...spec.opponents];
    this.lastResult = null;
    this.undoStack = [];
    this.mulliganOpen = true;
    this.trapNotes = notes;
    return this.table;
  }

  spendTrap(name) { this.stats.trapsUsed[name] = (this.stats.trapsUsed[name] ?? 0) + 1; }

  spendFiller(name) { this.stats.fillersUsed[name] = (this.stats.fillersUsed[name] ?? 0) + 1; }

  get myTurn() {
    const t = this.table;
    return Boolean(t) && t.state === PLAYING && t.current === HUMAN;
  }

  get gameOver() { return Boolean(this.table) && this.table.state !== PLAYING; }

  requireTurn() {
    if (!this.table || this.table.state !== PLAYING) throw new Error("No game in progress. Pick a table.");
    if (this.table.current !== HUMAN) throw new Error("It is not your turn.");
    return this.table;
  }

  get canUndo() {
    const last = this.undoStack[this.undoStack.length - 1];
    return Boolean(last) && this.myTurn && last.refills === this.table.refills;
  }

  undo() {
    if (!this.canUndo) throw new Error("Nothing to undo (undo never crosses a fresh draw or a discard).");
    this.table = this.undoStack.pop().table;
  }

  play(source, build) {
    const table = this.requireTurn();
    this.undoStack.push({ table: table.clone(), refills: table.refills });
    const refills = table.refills;
    try {
      table.play(source, build);
    } catch (err) {
      this.undoStack.pop();
      throw err;
    }
    this.mulliganOpen = false;
    if (table.refills !== refills) this.undoStack = [];
    this.afterHumanAction();
  }

  /** Discard to end your turn. Opponents are then run by the caller. */
  discard(handIndex, pile) {
    const table = this.requireTurn();
    table.discard(handIndex, pile);
    this.undoStack = [];
    this.mulliganOpen = false;
  }

  /** Play one opponent's whole turn. False once it is your turn or over. */
  opponentStep() {
    const t = this.table;
    if (!t || t.state !== PLAYING || t.current === HUMAN) return false;
    takeTurn(t, this.levels[t.current]);
    if (t.state === PLAYING && t.current === HUMAN) this.afterHumanAction();
    return t.state === PLAYING && t.current !== HUMAN;
  }

  runOpponents() {
    while (this.opponentStep()) { /* until your turn */ }
  }

  afterHumanAction() {
    const t = this.table;
    if (!(this.autoStock && t.state === PLAYING && t.current === HUMAN)) return;
    const seat = t.seat;
    while (t.state === PLAYING && seat.stockTop !== null && seat.stockTop !== WILD) {
      const fit = [0, 1, 2, 3].filter((b) => t.fits(seat.stockTop, b));
      if (!fit.length) break;
      this.undoStack = [];
      t.play(["stock", 0], fit[0]);
    }
  }

  /** The computer plays your turn; opponents are then run by the caller. */
  autoTurn() {
    const table = this.requireTurn();
    this.undoStack = [];
    takeTurn(table, "hard");
    this.mulliganOpen = false;
  }

  autoGame() {
    this.requireTurn();
    this.undoStack = [];
    autoplay(this.table, this.levels);
  }

  /** A suggested move: {text, source, build} or {text, discard: [hand, pile]}. */
  hint() {
    const table = this.requireTurn();
    const plan = bestPlan(table, "hard");
    if (plan.length) {
      const [kind, value, build] = plan[0];
      const what = kind === "hand" ? `your ${value === WILD ? "W" : value} from hand`
        : kind === "stock" ? "your stockpile card" : `the top of discard pile ${value + 1}`;
      const reaches = plan[plan.length - 1][0] === "stock" && kind !== "stock"
        ? " -- it opens up your stockpile" : "";
      const source = kind === "hand" ? ["hand", table.seat.hand.indexOf(value)] : [kind, value];
      return { text: `Play ${what} onto build ${build + 1}${reaches}.`, source, build };
    }
    const [i, p] = chooseDiscard(table, "hard");
    const card = table.seat.hand[i];
    return {
      text: `Nothing worth playing. Discard your ${card === WILD ? "W" : card} onto discard pile ${p + 1}.`,
      discard: [i, p],
    };
  }

  mulligan() {
    const table = this.requireTurn();
    if (!this.mulliganOpen) throw new Error("A mulligan is only allowed before your first move.");
    if (!this.pending(MULLIGAN)) throw new Error("You have no Mulligans.");
    const seat = table.seat;
    const keepWilds = seat.hand.filter((c) => c === WILD).length;
    table.drawPile.unshift(...seat.hand.filter((c) => c !== WILD));
    seat.hand = Array(keepWilds).fill(WILD);
    table.rng.shuffle(table.drawPile);
    table.refill(seat);
    this.spendFiller(MULLIGAN);
    this.mulliganOpen = false;
    this.undoStack = [];
  }

  spareWild() {
    const table = this.requireTurn();
    if (!this.pending(SPARE_WILD)) throw new Error("You have no Spare Wilds.");
    table.seat.hand.push(WILD);
    this.spendFiller(SPARE_WILD);
    this.undoStack = [];
  }

  forfeit() {
    if (!this.table || this.table.state !== PLAYING) throw new Error("No game in progress.");
    this.table.state = "stalled";
    this.table.winner = null;
    this.table.events.push({ seat: HUMAN, text: "forfeits" });
  }

  /** Bank a finished game into the stats. Idempotent. */
  settle() {
    const table = this.table;
    if (!table || table.state === PLAYING || this.lastResult) return this.lastResult;
    const me = table.seats[HUMAN];
    const won = table.winner === HUMAN;
    const spec = TABLES[this.tableNumber];
    const dominant = won && table.seats.slice(1).every((s) => s.stock.length * 2 >= spec.stock);
    const st = this.stats;
    st.gamesPlayed += 1;
    st.stockPlayed += me.stockPlayed;
    st.piles += me.pilesCompleted;
    if (me.pilesCompleted) st.tablesPiled.add(this.tableNumber);
    if (won) {
      st.gamesWon += 1;
      st.tablesWon.add(this.tableNumber);
    }
    if (dominant) st.tablesDominant.add(this.tableNumber);
    this.lastResult = {
      table: this.tableNumber, won, dominant, stockLeft: me.stock.length, turns: table.turns,
      winner: table.winner !== null ? table.seats[table.winner].name : null,
    };
    st.history.push({ table: this.tableNumber, won, dominant, left: me.stock.length });
    this.undoStack = [];
    return this.lastResult;
  }

  // -- checks --------------------------------------------------------------
  live() {
    if (!this.table || this.lastResult) return [0, 0];
    const me = this.table.seats[HUMAN];
    return [me.stockPlayed, me.pilesCompleted];
  }

  earned() {
    const names = [];
    const [liveStock, livePiles] = this.live();
    const stock = this.stats.stockPlayed + liveStock;
    const piles = this.stats.piles + livePiles;
    const st = this.stats;
    for (const n of GAMES_WON_MILESTONES) if (st.gamesWon >= n) names.push(gamesWonName(n));
    for (const n of STOCK_PLAYED_MILESTONES) if (stock >= n) names.push(stockPlayedName(n));
    for (const n of PILES_MILESTONES) if (piles >= n) names.push(pilesName(n));
    const piled = new Set(st.tablesPiled);
    if (livePiles) piled.add(this.tableNumber);
    for (const t of piled) names.push(tableLocationName(t, "Pile Completed"));
    for (const t of st.tablesWon) names.push(tableLocationName(t, "Won"));
    for (const t of st.tablesDominant) names.push(tableLocationName(t, "Dominant"));
    for (const s of st.bought) names.push(storeLocationName(s));
    const valid = new Set();
    for (let t = 1; t <= TABLE_COUNT; t += 1) for (const tier of this.tiers) valid.add(tableLocationName(t, tier));
    return new Set(names.filter((n) => !n.startsWith("Table ") || valid.has(n))
      .map((n) => LOCATION_NAME_TO_ID[n]));
  }

  newChecks() {
    const fresh = [...this.earned()].filter((id) => !this.reported.has(id)).sort((a, b) => a - b);
    for (const id of fresh) this.reported.add(id);
    return fresh;
  }

  get goalMet() {
    if (this.goal === GOAL_TABLE_TEN) return this.stats.tablesWon.has(10);
    if (this.goal === GOAL_ALL_TABLES) return this.stats.tablesWon.size === TABLE_COUNT;
    return this.stats.gamesWon >= this.gamesToWin;
  }

  get goalText() {
    if (this.goal === GOAL_TABLE_TEN) return "Goal: win at Table 10";
    if (this.goal === GOAL_ALL_TABLES) return `Goal: win at every table (${this.stats.tablesWon.size}/${TABLE_COUNT})`;
    return `Goal: win ${this.gamesToWin} games (${this.stats.gamesWon}/${this.gamesToWin})`;
  }
}
