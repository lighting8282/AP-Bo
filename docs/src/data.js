// Names, IDs and tables shared with the Python world. Mirrors skipbo/data.py
// and skipbo/game/tables.py; docs/test/tables_test.mjs fails if they drift.

export const GAME_NAME = "AP_SkipBo";
export const TABLE_COUNT = 10;

export const tableUnlock = (t) => `Table ${t} Unlocked`;

export const DISCARD_PILE = "Extra Discard Pile";
export const HAND_SIZE = "Hand Size Upgrade";
export const SKIPBO_CARD = "Skip-Bo Card";
export const STOCK_SHRINK = "Stockpile Shrink";
export const POWER_ITEMS = [DISCARD_PILE, HAND_SIZE, SKIPBO_CARD, STOCK_SHRINK];

export const STACKED_STOCK = "Stacked Stockpile";
export const LOCKED_DISCARD = "Locked Discard";
export const RIVAL_WILD = "Rival Wild";
export const MULLIGAN = "Mulligan";
export const SPARE_WILD = "Spare Wild";
export const AP_POINT = "AP Point";

export const TRAPS = [STACKED_STOCK, LOCKED_DISCARD, RIVAL_WILD];
export const FILLERS = [MULLIGAN, SPARE_WILD];

export const BASE_DISCARD_PILES = 2;
export const BASE_HAND_SIZE = 5;
export const SHRINK_STEP = 2;
export const MIN_STOCK = 5;
export const STACK_STEP = 3;
export const POWER_CAPS = { [DISCARD_PILE]: 2, [HAND_SIZE]: 2, [SKIPBO_CARD]: 4, [STOCK_SHRINK]: 3 };

export const ITEM_NAME_TO_ID = {
  ...Object.fromEntries(Array.from({ length: TABLE_COUNT }, (_, i) => [tableUnlock(i + 1), i + 1])),
  [DISCARD_PILE]: 50,
  [HAND_SIZE]: 51,
  [SKIPBO_CARD]: 52,
  [STOCK_SHRINK]: 53,
  [STACKED_STOCK]: 60,
  [LOCKED_DISCARD]: 61,
  [RIVAL_WILD]: 62,
  [MULLIGAN]: 70,
  [SPARE_WILD]: 71,
  [AP_POINT]: 72,
};

export const TIERS = ["Pile Completed", "Won", "Dominant"];
export const GAMES_WON_MILESTONES = [1, 2, 3, 5, 8, 12, 16, 20];
export const STOCK_PLAYED_MILESTONES = [10, 25, 50, 100, 150, 200];
export const PILES_MILESTONES = [1, 3, 6, 10, 15, 25];

export const STORE_PRICES = [1, 1, 1, 1, 2, 2, 3, 3];
export const MAX_STORE_SLOTS = STORE_PRICES.length;
export const STORE_SLACK = 2;

export const storeGate = (slot) => STORE_PRICES.slice(0, slot).reduce((a, b) => a + b, 0);
export const tableLocationName = (t, tier) => `Table ${t} - ${tier}`;
export const gamesWonName = (n) => `Games Won: ${n}`;
export const stockPlayedName = (n) => `Stockpile Cards Played: ${n}`;
export const pilesName = (n) => `Build Piles Completed: ${n}`;
export const storeLocationName = (s) => `Store Slot ${s}`;

export const LOCATION_NAME_TO_ID = (() => {
  const out = {};
  for (let t = 1; t <= TABLE_COUNT; t += 1) {
    TIERS.forEach((tier, i) => { out[tableLocationName(t, tier)] = 100 + t * 10 + i; });
  }
  GAMES_WON_MILESTONES.forEach((n, i) => { out[gamesWonName(n)] = 300 + i; });
  STOCK_PLAYED_MILESTONES.forEach((n, i) => { out[stockPlayedName(n)] = 330 + i; });
  PILES_MILESTONES.forEach((n, i) => { out[pilesName(n)] = 360 + i; });
  for (let s = 1; s <= MAX_STORE_SLOTS; s += 1) out[storeLocationName(s)] = 500 + s;
  return out;
})();

/** The ten tables: opponent AI levels, and stockpile size. */
export const TABLES = {
  1: { opponents: ["easy"], stock: 10 },
  2: { opponents: ["easy", "easy"], stock: 10 },
  3: { opponents: ["normal"], stock: 10 },
  4: { opponents: ["easy", "easy", "easy"], stock: 15 },
  5: { opponents: ["normal", "normal"], stock: 15 },
  6: { opponents: ["hard"], stock: 15 },
  7: { opponents: ["normal", "normal", "normal"], stock: 20 },
  8: { opponents: ["hard", "hard"], stock: 20 },
  9: { opponents: ["hard", "hard", "hard"], stock: 25 },
  10: { opponents: ["hard", "hard", "hard"], stock: 30 },
};

export function describeTable(t) {
  const spec = TABLES[t];
  const counts = new Map();
  for (const level of spec.opponents) counts.set(level, (counts.get(level) ?? 0) + 1);
  const who = [...counts].map(([level, n]) => `${n} ${level}`).join(", ");
  const plural = spec.opponents.length > 1 ? "s" : "";
  return `vs ${who} opponent${plural}, ${spec.stock}-card stockpiles`;
}
