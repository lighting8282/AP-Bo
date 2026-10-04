// Replay Python-recorded games through the JS engine and AI.
// Regenerate the fixture with `python tools/export_traces.py`.

import { readFileSync } from "node:fs";

import { autoplay } from "../src/ai.js";
import { Seat, Table } from "../src/engine.js";
import { ScriptedRng } from "./scripted_rng.mjs";

const games = JSON.parse(readFileSync(new URL("./traces.json", import.meta.url), "utf8"));
let failures = 0;
let events = 0;

for (const g of games) {
  const rng = new ScriptedRng(g.rng);
  const seats = g.levels.map((_, i) => new Seat(`S${i}`, [], {
    handSize: g.handSizes[i], discardSlots: g.slots[i],
  }));
  const bonus = Object.fromEntries(Object.entries(g.bonus).map(([k, v]) => [k, v]));
  let problem = null;
  let table = null;
  try {
    table = Table.deal(rng, seats, g.stocks, { bonusWilds: bonus });
    autoplay(table, g.levels);
  } catch (err) {
    problem = `threw: ${err.message}`;
  }
  if (!problem) {
    const js = table.events.map((e) => [e.seat, e.text]);
    for (let i = 0; i < Math.max(js.length, g.events.length); i += 1) {
      if (JSON.stringify(js[i]) !== JSON.stringify(g.events[i])) {
        problem = `event ${i}: python ${JSON.stringify(g.events[i])} js ${JSON.stringify(js[i])}`;
        break;
      }
    }
    events += js.length;
  }
  if (!problem) {
    const f = g.final;
    const mine = {
      state: table.state, winner: table.winner, turns: table.turns, builds: table.builds,
      seats: table.seats.map((s) => ({
        stock: s.stock, hand: s.hand, discards: s.discards, stockPlayed: s.stockPlayed,
        wildsPlayed: s.wildsPlayed, pilesCompleted: s.pilesCompleted, cardsPlayed: s.cardsPlayed,
      })),
    };
    if (JSON.stringify(mine) !== JSON.stringify(f)) problem = "final state differs";
    else if (rng.at !== g.rng.length) problem = `JS used ${rng.at} of ${g.rng.length} rng calls`;
  }
  if (problem) {
    failures += 1;
    console.log(`game ${g.seed} (${g.levels.join("/")}): ${problem}`);
  }
}

console.log(`crosscheck: ${games.length} games, ${events} events, ${failures} mismatches`);
process.exit(failures ? 1 : 0);
