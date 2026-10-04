// Computer players and the Hint/Auto planner. A port of skipbo/game/ai.py
// that has to agree with it move for move: the iteration order, the memo key
// (zero counts included, as Python's Counter keeps them) and the strict
// tie-breaking are all deliberate copies.

import { MAX_RANK, WILD } from "./cards.js?v=040ed05b";
import { BUILD_PILES, MAX_DISCARD_PILES, PLAYING } from "./engine.js?v=040ed05b";

export const DEPTH = { easy: 1, normal: 3, hard: 8 };
export const NODE_LIMIT = 6000;

const advance = (needed) => (needed === MAX_RANK ? 1 : needed + 1);

function counter(cards) {
  const m = new Map();
  for (const c of cards) m.set(c, (m.get(c) ?? 0) + 1);
  return m;
}

function handKey(hand) {
  return [...hand.entries()].sort((a, b) => a[0] - b[0]).map(([k, v]) => `${k}:${v}`).join(",");
}

/** Plan steps are [kind, valueOrPile, build]. */
export function bestPlan(table, level = "hard") {
  if (level === "easy") return easyPlan(table);
  const seat = table.seat;
  const depth = DEPTH[level];
  const stock = seat.stockTop;
  const needed0 = Array.from({ length: BUILD_PILES }, (_, b) => table.needed(b));
  const hand0 = counter(seat.hand);
  const piles0 = seat.discards.map((d) => [...d]);
  const nxt = table.seats[(table.current + 1) % table.seats.length].stockTop;
  const avoid = level === "hard" && table.seats.length > 1;

  let best = [0, []];
  const seen = new Set();
  let nodes = 0;

  const scoreEnd = (needed, hand, wilds, fromHand, fromPiles) => {
    let value = fromHand * 2 + fromPiles * 2.5 - wilds * 6;
    let total = 0;
    for (const v of hand.values()) total += v;
    if (total === 0 && fromHand) value += 8;
    if (avoid && nxt !== null) {
      value -= 5 * needed.filter((n) => nxt === WILD || n === nxt).length;
    }
    return value;
  };

  const search = (needed, hand, piles, path, wilds, fromHand, fromPiles) => {
    nodes += 1;
    if (stock !== null) {
      for (let b = 0; b < BUILD_PILES; b += 1) {
        if (stock === WILD || needed[b] === stock) {
          const score = 1000 - wilds * 3 + fromPiles + (stock === WILD ? -1 : 0);
          if (score > best[0]) best = [score, [...path, ["stock", 0, b]]];
          return;
        }
      }
    }
    const score = scoreEnd(needed, hand, wilds, fromHand, fromPiles);
    if (score > best[0]) best = [score, [...path]];
    if (path.length >= depth || nodes > NODE_LIMIT) return;
    const key = `${needed.join(",")}|${handKey(hand)}|${piles.map((p) => p.join(",")).join("/")}`;
    if (seen.has(key)) return;
    seen.add(key);

    for (let b = 0; b < BUILD_PILES; b += 1) {
      const n = needed[b];
      if (b && needed.slice(0, b).includes(n)) continue;
      const nn = [...needed];
      nn[b] = advance(n);
      if (hand.get(n)) {
        hand.set(n, hand.get(n) - 1);
        search(nn, hand, piles, [...path, ["hand", n, b]], wilds, fromHand + 1, fromPiles);
        hand.set(n, hand.get(n) + 1);
      }
      for (let p = 0; p < MAX_DISCARD_PILES; p += 1) {
        const pile = piles[p];
        if (pile.length && (pile[pile.length - 1] === n || pile[pile.length - 1] === WILD)) {
          const w = pile[pile.length - 1] === WILD ? 1 : 0;
          const np = [...piles];
          np[p] = pile.slice(0, -1);
          search(nn, hand, np, [...path, ["discard", p, b]], wilds + w, fromHand, fromPiles + 1);
        }
      }
      if (hand.get(WILD)) {
        hand.set(WILD, hand.get(WILD) - 1);
        search(nn, hand, piles, [...path, ["hand", WILD, b]], wilds + 1, fromHand + 1, fromPiles);
        hand.set(WILD, hand.get(WILD) + 1);
      }
    }
  };

  search(needed0, hand0, piles0, [], 0, 0, 0);
  return best[1];
}

function easyPlan(table) {
  const seat = table.seat;
  for (let b = 0; b < BUILD_PILES; b += 1) {
    if (seat.stockTop !== null && table.fits(seat.stockTop, b)) return [["stock", 0, b]];
  }
  for (let b = 0; b < BUILD_PILES; b += 1) {
    const n = table.needed(b);
    if (seat.hand.includes(n) && table.rng.random() < 0.6) return [["hand", n, b]];
  }
  return [];
}

export function resolve(table, [kind, value]) {
  if (kind === "hand") return ["hand", table.seat.hand.indexOf(value)];
  return [kind, value];
}

/** [hand index, discard pile] to end the turn with. */
export function chooseDiscard(table, level = "hard") {
  const seat = table.seat;
  const piles = Array.from({ length: seat.discardSlots }, (_, p) => p);
  if (level === "easy") {
    let naturals = seat.hand.map((c, i) => [c, i]).filter(([c]) => c !== WILD).map(([, i]) => i);
    if (!naturals.length) naturals = seat.hand.map((_, i) => i);
    const i = table.rng.choice(naturals);
    return [i, table.rng.choice(piles)];
  }

  const stock = seat.stockTop;
  const needed = Array.from({ length: BUILD_PILES }, (_, b) => table.needed(b));
  let best = [0, 0];
  let bestScore = -Infinity;
  seat.hand.forEach((card, i) => {
    let keep = 0;
    if (card === WILD) keep = 40;
    else if (stock !== null && stock !== WILD && card < stock) keep = 3 + (stock - card <= 3 ? 3 : 0);
    keep += needed.includes(card) ? 4 : 0;
    for (const p of piles) {
      const top = seat.discardTop(p);
      let fit;
      if (top === null) fit = 4 + (piles.filter((q) => !seat.discards[q].length).length - 1) * 1.5;
      else if (top === card) fit = 8;
      else if (top === card + 1) fit = 7.5;
      else if (top !== WILD && top > card) fit = 4 - (top - card) * 0.3;
      else fit = -2 - seat.discards[p].length * 0.5;
      const score = fit - keep + card * 0.05;
      if (score > bestScore) {
        best = [i, p];
        bestScore = score;
      }
    }
  });
  return best;
}

/** Play one whole turn for the current seat. */
export function takeTurn(table, level) {
  const me = table.current;
  let guard = 0;
  while (table.state === PLAYING && table.current === me && guard < 60) {
    guard += 1;
    const plan = bestPlan(table, level);
    if (!plan.length) break;
    const refills = table.refills;
    let interrupted = false;
    for (const step of plan) {
      table.play(resolve(table, step), step[2]);
      if (table.state !== PLAYING || table.refills !== refills || step[0] === "stock") {
        interrupted = true;
        break;
      }
    }
    if (!interrupted && plan[plan.length - 1][0] !== "stock") break;
  }
  if (table.state === PLAYING && table.current === me) {
    if (table.seat.hand.length) table.discard(...chooseDiscard(table, level));
    else table.passTurn();
  }
}

export function autoplay(table, levels, untilSeat = null) {
  while (table.state === PLAYING) {
    if (untilSeat !== null && table.current === untilSeat) return;
    takeTurn(table, levels[table.current]);
  }
}
