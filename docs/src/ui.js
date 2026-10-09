// The page. Reads the session, acts only through it and the client, and
// redraws the whole board after every change -- it is a few dozen elements.
//
// Input model (same as the desktop tab): tap a source to select it, and the
// build piles it fits light up; tap one to play. Tapping the selected card
// again sends it to the first pile it fits. A selected hand card plus a tap
// on one of your discard piles discards it and ends the turn.

import { WILD, cardFile, cardName } from "./cards.js?v=e59d38d1";
import {
  MULLIGAN, SPARE_WILD, STOCK_SHRINK, STORE_PRICES, TABLES, TIERS, describeTable,
} from "./data.js?v=e59d38d1";
import { BUILD_PILES, MAX_DISCARD_PILES, PLAYING, WON } from "./engine.js?v=e59d38d1";
import { HUMAN } from "./session.js?v=e59d38d1";
import { BoClient } from "./client.js?v=e59d38d1";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const ui = {
  selected: null,       // ["hand", i] | ["stock", 0] | ["discard", p]
  hint: null,           // the last hint, until anything else happens
  busy: false,          // opponents are moving
  eventCursor: 0,
  eventGame: -1,
};

const client = new BoClient({
  onUpdate: () => render(),
  onLog: (text) => log(text, "sys"),
  onMessage: (text) => log(text, "room"),
});
const session = () => client.session;

// -- log ---------------------------------------------------------------------
function log(text, cls = "") {
  const box = $("log");
  const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
  const line = el("div", cls, text);
  box.append(line);
  while (box.childElementCount > 400) box.firstElementChild.remove();
  if (stick) box.scrollTop = box.scrollHeight;
}

function drainEvents() {
  const s = session();
  const t = s.table;
  if (!t) return;
  if (s.gameId !== ui.eventGame) {
    ui.eventGame = s.gameId;
    ui.eventCursor = 0;
  }
  ui.eventCursor = Math.min(ui.eventCursor, t.events.length); // an undo shortens it
  for (const e of t.events.slice(ui.eventCursor)) {
    if (e.seat === HUMAN) {
      const [verb, ...rest] = e.text.split(" ");
      log(`You ${verb.endsWith("s") ? verb.slice(0, -1) : verb} ${rest.join(" ")}`.trim(), "you");
    } else {
      log(e.seat < 0 ? e.text : `${t.seats[e.seat].name} ${e.text}`);
    }
  }
  ui.eventCursor = t.events.length;
}

// -- actions -----------------------------------------------------------------
function attempt(fn) {
  try {
    fn();
    return true;
  } catch (err) {
    log(err.message, "sys");
    render();
    return false;
  } finally {
    drainEvents();
  }
}

/** Run each opponent's turn with a pause between, so you can follow it. */
async function runOpponents() {
  const s = session();
  const delay = Number($("speed").value);
  ui.busy = true;
  render();
  while (s.table && s.table.state === PLAYING && s.table.current !== HUMAN) {
    if (delay) await new Promise((r) => setTimeout(r, delay));
    if (s !== session()) return; // reconnected mid-turn
    s.opponentStep();
    drainEvents();
    render();
  }
  ui.busy = false;
  client.afterAction();
  drainEvents();
}

function act(name) {
  const s = session();
  ui.hint = null;
  ui.selected = null;
  switch (name) {
    case "hint":
      attempt(() => { ui.hint = s.hint(); });
      break;
    case "undo":
      attempt(() => s.undo());
      break;
    case "auto":
      if (attempt(() => s.autoTurn())) runOpponents();
      break;
    case "autogame":
      attempt(() => s.autoGame());
      break;
    case "mulligan":
      if (attempt(() => s.mulligan())) client.save();
      break;
    case "wild":
      if (attempt(() => s.spareWild())) client.save();
      break;
    case "autostock":
      client.setAutoStock(!s.autoStock);
      drainEvents();
      break;
    case "forfeit":
      if (!window.confirm("Forfeit this game? It counts as a loss.")) return;
      attempt(() => s.forfeit());
      break;
    default:
      return;
  }
  client.afterAction();
}

function startTable(n) {
  ui.selected = null;
  ui.hint = null;
  const s = session();
  if (s.table && s.table.state === PLAYING) {
    if (!window.confirm("Leave the current game? It counts as a loss.")) return;
    s.forfeit();
    client.afterAction();
  }
  if (attempt(() => s.start(n))) {
    log(`-- Table ${n}: ${describeTable(n)}`, "sys");
    for (const note of s.trapNotes) log(`TRAP: ${note}`, "sys");
    client.save();
    s.afterHumanAction();
    drainEvents();
  }
  client.afterAction();
}

const sameSource = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];

function select(source) {
  const s = session();
  if (ui.busy || !s.myTurn) return;
  const t = s.table;
  const card = t.sourceCard(source);
  if (card === null) return;
  ui.hint = null;
  if (sameSource(ui.selected, source)) {
    ui.selected = null;
    const fits = [0, 1, 2, 3].filter((b) => t.fits(card, b));
    if (fits.length) play(source, fits[0]);
    else render();
    return;
  }
  ui.selected = source;
  render();
}

function play(source, build) {
  if (attempt(() => session().play(source, build))) client.afterAction();
}

function clickBuild(b) {
  if (!ui.selected || ui.busy) return;
  const source = ui.selected;
  ui.selected = null;
  play(source, b);
}

function clickDiscard(p) {
  if (ui.busy) return;
  const s = session();
  if (ui.selected && ui.selected[0] === "hand") {
    const [, i] = ui.selected;
    ui.selected = null;
    if (attempt(() => s.discard(i, p))) runOpponents();
    return;
  }
  select(["discard", p]);
}

// -- rendering ---------------------------------------------------------------
function cardEl(card, { cls = "", empty = "", mini = false, onClick = null, count = null } = {}) {
  const node = el(onClick ? "button" : "div", `card ${mini ? "mini " : ""}${cls}`);
  if (onClick) {
    node.type = "button";
    node.addEventListener("click", onClick);
  }
  if (card === null || card === undefined) {
    node.classList.add("empty");
    node.textContent = empty;
    node.setAttribute("aria-label", empty || "empty");
  } else {
    const img = el("img");
    img.src = `assets/cards/${cardFile(card)}`;
    img.alt = card === WILD ? "Wild" : String(card);
    img.draggable = false;
    node.append(img);
  }
  if (count !== null) node.append(el("span", "count", String(count)));
  return node;
}

function targets(t) {
  if (!t || !ui.selected) return new Set();
  const card = t.sourceCard(ui.selected);
  if (card === null) return new Set();
  return new Set([0, 1, 2, 3].filter((b) => t.fits(card, b)));
}

function render() {
  const s = session();
  const t = s.table;
  if (t && ui.selected && (!s.myTurn || t.sourceCard(ui.selected) === null)) ui.selected = null;
  renderHeader(s);
  renderSummary(s);
  renderOpponents(t);
  renderBuilds(t);
  renderMine(t);
  renderHand(t);
  renderPrompt(s, t);
  renderActions(s, t);
  renderTables(s);
  renderStore(s);
}

function renderHeader() {
  const status = $("status");
  if (client.connected) {
    status.textContent = `connected as ${$("slot").value}`;
    status.className = "ok";
  } else if (client.offline) {
    status.textContent = "free play";
    status.className = "ok";
  } else {
    status.textContent = "not connected";
    status.className = "";
  }
  const playing = client.connected || client.offline;
  $("connect").hidden = playing && !ui.editing;
  $("edit-connection").hidden = !playing || ui.editing;
  $("say").hidden = !client.connected;
  $("new-run").hidden = !client.offline;
}

function renderSummary(s) {
  const box = $("summary");
  box.replaceChildren();
  const add = (html) => {
    const span = el("span", "chip");
    span.innerHTML = html;
    box.append(span);
  };
  add(`<b>${s.goalText}</b>`);
  add(`won <b>${s.stats.gamesWon}</b>/${s.stats.gamesPlayed}`);
  add(`discard piles <b>${s.discardPiles}</b>`);
  add(`hand <b>${s.handSize}</b>`);
  add(`Bo cards <b>${s.bonusWilds}</b>`);
  add(`shrinks <b>${s.count(STOCK_SHRINK)}</b>`);
  if (s.pending(MULLIGAN)) add(`mulligans <b>${s.pending(MULLIGAN)}</b>`);
  if (s.pending(SPARE_WILD)) add(`spare wilds <b>${s.pending(SPARE_WILD)}</b>`);
}

function renderOpponents(t) {
  const box = $("opponents");
  box.replaceChildren();
  if (!t) return;
  t.seats.slice(1).forEach((seat, k) => {
    const i = k + 1;
    const turn = t.state === PLAYING && t.current === i;
    const opp = el("div", `opp${turn ? " turn" : ""}`);
    const name = el("div", "name");
    name.append(el("b", "", seat.name));
    name.append(el("span", "", `${TABLES[session().tableNumber].opponents[k]} · hand ${seat.hand.length}${turn ? " · playing" : ""}`));
    opp.append(name);
    const cards = el("div", "cards");
    cards.append(cardEl(seat.stockTop, { empty: "out", count: seat.stock.length }));
    cards.append(el("span", "sep"));
    for (let p = 0; p < MAX_DISCARD_PILES; p += 1) {
      cards.append(cardEl(seat.discardTop(p), { mini: true, count: seat.discards[p].length || null }));
    }
    opp.append(cards);
    box.append(opp);
  });
}

function renderBuilds(t) {
  const box = $("builds");
  box.replaceChildren();
  const glow = targets(t);
  for (let b = 0; b < BUILD_PILES; b += 1) {
    const pile = el("div", "pile");
    if (!t) {
      pile.append(el("span", "label", `#${b + 1}`), cardEl(null, { empty: "--" }));
      box.append(pile);
      continue;
    }
    const top = t.builds[b].length ? t.builds[b][t.builds[b].length - 1] : null;
    const label = el("span", "label");
    label.innerHTML = `needs <b>${t.needed(b)}</b>`;
    let cls = glow.has(b) ? "target" : "";
    if (ui.hint && ui.hint.build === b) cls += " hinted";
    pile.append(label, cardEl(top, {
      cls, empty: "", onClick: () => clickBuild(b), count: t.builds[b].length || null,
    }));
    box.append(pile);
  }
  $("pile-info").textContent = t ? `deck ${t.drawPile.length} · set aside ${t.setAside.length} · turn ${t.turns + 1}` : "";
}

function renderMine(t) {
  const box = $("mine");
  box.replaceChildren();
  if (!t) {
    box.append(el("p", "", "No game in progress -- pick a table below."));
    return;
  }
  const me = t.seats[HUMAN];
  const hint = ui.hint?.source;
  const stock = el("div", "pile stock");
  stock.append(el("span", "label", `Stockpile (${me.stock.length})`));
  stock.append(cardEl(me.stockTop, {
    cls: `${sameSource(ui.selected, ["stock", 0]) ? "selected" : ""} ${sameSource(hint, ["stock", 0]) ? "hinted" : ""}`,
    empty: "empty", onClick: () => select(["stock", 0]),
  }));
  box.append(stock, el("span", "gap"));

  const handSelected = ui.selected && ui.selected[0] === "hand";
  for (let p = 0; p < MAX_DISCARD_PILES; p += 1) {
    const locked = p >= me.discardSlots;
    const stack = me.discards[p];
    const pile = el("div", "pile");
    pile.append(el("span", "label", locked ? "locked" : `Discard ${p + 1}`));
    let cls = "";
    if (locked) cls = "locked";
    else if (sameSource(ui.selected, ["discard", p])) cls = "selected";
    else if (handSelected) cls = "discard-ok";
    if (sameSource(hint, ["discard", p]) || (ui.hint?.discard && ui.hint.discard[1] === p)) cls += " hinted";
    pile.append(cardEl(stack.length ? stack[stack.length - 1] : null, {
      cls, empty: locked ? "locked" : "empty", count: stack.length > 1 ? stack.length : null,
      onClick: locked ? null : () => clickDiscard(p),
    }));
    // What is buried under the top, so you can plan a dig.
    pile.append(el("span", "under", stack.slice(-5, -1).reverse().map(cardName).join(" ")));
    box.append(pile);
  }
}

function renderHand(t) {
  const box = $("hand");
  box.replaceChildren();
  if (!t) return;
  const me = t.seats[HUMAN];
  const myTurn = session().myTurn && !ui.busy;
  const hint = ui.hint?.source;
  me.hand.forEach((card, i) => {
    let cls = "";
    if (sameSource(ui.selected, ["hand", i])) cls = "selected";
    else if (myTurn && [0, 1, 2, 3].some((b) => t.fits(card, b))) cls = "playable";
    if (sameSource(hint, ["hand", i]) || (ui.hint?.discard && ui.hint.discard[0] === i)) cls += " hinted";
    box.append(cardEl(card, { cls, onClick: () => select(["hand", i]) }));
  });
}

function renderPrompt(s, t) {
  const box = $("prompt");
  box.replaceChildren();
  const span = (cls, text) => box.append(el("span", cls, text));
  if (!t) {
    box.textContent = client.connected || client.offline
      ? "Pick a table to sit down."
      : "Connect to your Archipelago room, or press Just play.";
  } else if (t.state === WON) {
    if (t.winner === HUMAN) span("win", "You win! ");
    else span("lose", `${t.seats[t.winner].name} wins. `);
    box.append("Pick a table to play again.");
  } else if (t.state !== PLAYING) {
    span("lose", "Game over -- nobody won. ");
    box.append("Pick a table.");
  } else if (ui.busy || !s.myTurn) {
    box.textContent = `${t.seat.name} is playing...`;
  } else if (ui.hint && !ui.selected) {
    span("hint", "Hint: ");
    box.append(ui.hint.text);
  } else if (ui.selected) {
    const card = t.sourceCard(ui.selected);
    box.append(`Selected ${cardName(card)} -- tap a glowing build pile`
      + `${ui.selected[0] === "hand" ? ", or one of your discard piles to end your turn" : ""}.`);
  } else {
    box.append("Your turn. Play onto the build piles; end your turn by discarding a hand card.");
  }
}

function renderActions(s, t) {
  const playing = s.myTurn && !ui.busy;
  const set = (name, enabled) => {
    document.querySelector(`[data-act="${name}"]`).disabled = !enabled;
  };
  set("hint", playing);
  set("undo", playing && s.canUndo);
  set("auto", playing);
  set("autogame", playing);
  set("mulligan", playing && s.mulliganOpen && s.pending(MULLIGAN) > 0);
  set("wild", playing && s.pending(SPARE_WILD) > 0);
  set("forfeit", Boolean(t) && t.state === PLAYING && !ui.busy);
  const auto = document.querySelector('[data-act="autostock"]');
  auto.setAttribute("aria-pressed", String(s.autoStock));
  auto.textContent = `Auto-stock ${s.autoStock ? "on" : "off"}`;
  document.querySelector('[data-act="mulligan"]').textContent = `Mulligan (${s.pending(MULLIGAN)})`;
  document.querySelector('[data-act="wild"]').textContent = `Spare Wild (${s.pending(SPARE_WILD)})`;
}

function renderTables(s) {
  const box = $("tables");
  box.replaceChildren();
  const st = s.stats;
  const have = [st.tablesPiled, st.tablesWon, st.tablesDominant];
  for (let n = 1; n <= 10; n += 1) {
    const b = el("button");
    b.type = "button";
    const marks = TIERS.map((tier, i) => (s.tiers.includes(tier) ? (have[i].has(n) ? tier[0] : "·") : ""))
      .join("");
    b.append(String(n), el("small", "", marks || " "));
    b.title = describeTable(n);
    const open = s.unlockedTables.has(n);
    b.className = st.tablesWon.has(n) ? "won" : open ? "open" : "";
    if (s.tableNumber === n && s.table && s.table.state === PLAYING) b.classList.add("current");
    b.disabled = !open || ui.busy;
    b.addEventListener("click", () => startTable(n));
    box.append(b);
  }
}

function renderStore(s) {
  const box = $("store");
  box.replaceChildren();
  if (!s.storeSlots) return;
  box.append(el("span", "", `Store: ${s.pointsLeft} pt(s)`));
  for (let slot = 1; slot <= s.storeSlots; slot += 1) {
    const bought = s.stats.bought.has(slot);
    const b = el("button", "small", bought ? `Slot ${slot} ✓` : `Slot ${slot} · ${STORE_PRICES[slot - 1]} pt`);
    b.type = "button";
    const refusal = bought ? "Bought" : s.canBuy(slot);
    b.disabled = Boolean(refusal);
    if (refusal) b.title = refusal;
    b.addEventListener("click", () => {
      try {
        client.buy(slot);
        log(`Bought store slot ${slot}.`, "sys");
      } catch (err) {
        log(err.message, "sys");
      }
      client.save();
    });
    box.append(b);
  }
}

// -- wiring ------------------------------------------------------------------
function remember(key, value) {
  try { localStorage.setItem(key, value); } catch { /* fine */ }
}
function recall(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

$("connect").addEventListener("submit", async (event) => {
  event.preventDefault();
  let url = $("url").value.trim();
  const slot = $("slot").value.trim();
  if (!url || !slot) {
    log("Enter the server address and your slot name.", "sys");
    return;
  }
  // The published page is HTTPS, which can only open wss:// sockets.
  if (!/^wss?:\/\//.test(url)) url = `${location.protocol === "https:" ? "wss" : "ws"}://${url}`;
  remember("apbo_url", $("url").value.trim());
  remember("apbo_slot", slot);
  $("connect-button").disabled = true;
  $("status").textContent = "connecting...";
  try {
    await client.connect(url, slot, $("password").value);
    ui.editing = false;
    ui.selected = null;
    ui.hint = null;
  } catch (err) {
    log(`Could not connect: ${err.message ?? err}`, "sys");
  } finally {
    $("connect-button").disabled = false;
    render();
  }
});

$("free-play").addEventListener("click", () => {
  ui.editing = false;
  client.startFreePlay();
});
$("new-run").addEventListener("click", () => {
  if (window.confirm("Reset your free-play stats?")) client.startFreePlay({ fresh: true });
});
$("edit-connection").addEventListener("click", () => {
  ui.editing = true;
  render();
});
$("say").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("say-text").value.trim();
  if (!text) return;
  client.client.messages.say(text).catch((err) => log(err.message, "sys"));
  $("say-text").value = "";
});
$("speed").value = recall("apbo_speed") ?? "350";
$("speed").addEventListener("change", () => remember("apbo_speed", $("speed").value));
$("actions").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-act]");
  if (button && !button.disabled) act(button.dataset.act);
});

document.addEventListener("keydown", (event) => {
  if (event.target.closest("input, select, textarea")) return;
  const key = event.key.toLowerCase();
  if (key === "escape") {
    ui.selected = null;
    render();
  } else if (/^[1-9]$/.test(key)) {
    select(["hand", Number(key) - 1]);
  } else if (key === "s") {
    select(["stock", 0]);
  } else if (key === "h") {
    act("hint");
  } else if (key === "u" || (key === "z" && (event.ctrlKey || event.metaKey))) {
    act("undo");
  } else if (key === "a") {
    act("auto");
  } else {
    return;
  }
  event.preventDefault();
});

// Prefill, and accept ?server=...&slot=... links (e.g. from a room page).
const params = new URLSearchParams(location.search);
$("url").value = params.get("server") ?? recall("apbo_url") ?? $("url").value;
$("slot").value = params.get("slot") ?? recall("apbo_slot") ?? "";
render();
