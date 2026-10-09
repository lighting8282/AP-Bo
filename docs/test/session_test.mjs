// The JS session against what the Python session decided.
// Regenerate the fixture with `python tools/export_session_fixtures.py`.

import { readFileSync } from "node:fs";

import { ITEM_NAME_TO_ID, LOCATION_NAME_TO_ID, TABLES, describeTable } from "../src/data.js";
import { BoSession, Stats } from "../src/session.js";
import { ScriptedRng } from "./scripted_rng.mjs";

const fx = JSON.parse(readFileSync(new URL("./session_fixtures.json", import.meta.url), "utf8"));
let checks = 0;
const failures = [];
function same(actual, expected, what) {
  checks += 1;
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    failures.push(`${what}\n    python ${JSON.stringify(expected)}\n    js     ${JSON.stringify(actual)}`);
  }
}

same(ITEM_NAME_TO_ID, fx.itemIds, "item ids");
same(LOCATION_NAME_TO_ID, fx.locationIds, "location ids");
for (const [n, t] of Object.entries(fx.tables)) {
  same({ opponents: TABLES[n].opponents, stock: TABLES[n].stock, description: describeTable(Number(n)) },
    t, `table ${n}`);
}

fx.configs.forEach((c, i) => {
  const s = new BoSession({});
  s.setItems(c.items);
  s.stats.trapsUsed = c.trapsUsed;
  s.stats.fillersUsed = c.fillersUsed;
  same({
    unlocked: [...s.unlockedTables].sort((a, b) => a - b),
    discardPiles: s.discardPiles, handSize: s.handSize, bonusWilds: s.bonusWilds,
    power: s.power, points: s.points,
    stockSizes: Object.fromEntries(Object.keys(TABLES).map((t) => [t, s.stockSize(Number(t))])),
    pending: Object.fromEntries(Object.keys(c.pending).map((n) => [n, s.pending(n)])),
  }, {
    unlocked: c.unlocked, discardPiles: c.discardPiles, handSize: c.handSize,
    bonusWilds: c.bonusWilds, power: c.power, points: c.points, stockSizes: c.stockSizes,
    pending: c.pending,
  }, `config ${i}`);
});

fx.earned.forEach((e, i) => {
  const s = new BoSession(e.slot);
  s.stats = Stats.fromPayload(e.payload);
  same([...s.earned()].sort((a, b) => a - b), e.earned, `earned ${i}`);
  same([s.goalMet, s.goalText], [e.goalMet, e.goalText], `goal ${i}`);
  same(s.stats.toPayload(), e.payload, `payload round trip ${i}`);
});

fx.payloads.forEach((p, i) => {
  const stats = Stats.fromPayload(p.input);
  same(stats ? stats.toPayload() : null, p.output, `payload case ${i}`);
});

fx.starts.forEach((st, i) => {
  const s = new BoSession({}, new ScriptedRng(st.rng));
  s.setItems(st.items);
  const t = s.start(st.table);
  same({
    notes: s.trapNotes, trapsUsed: s.stats.trapsUsed, levels: s.levels,
    seats: t.seats.map((x) => ({ stock: x.stock, hand: x.hand, slots: x.discardSlots, handSize: x.handSize })),
  }, { notes: st.notes, trapsUsed: st.trapsUsed, levels: st.levels, seats: st.seats }, `start ${i}`);
});

for (const f of failures.slice(0, 10)) console.log(`FAIL ${f}`);
console.log(`session: ${checks} checks, ${failures.length} mismatches`);
process.exit(failures.length ? 1 : 0);
