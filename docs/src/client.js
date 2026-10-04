// Archipelago wiring for the browser client. Mirrors skipbo/client/context.py:
// the session holds the game, this holds the socket, the UI reads both.
//
// Same save key and payload as the desktop client, so the two can take turns
// on one slot. Nothing is saved until the restore has landed, or the empty
// stats built on connect would overwrite the real ones.

import { Client } from "../node_modules/archipelago.js/dist/index.js?v=040ed05b";

import { DISCARD_PILE, GAME_NAME, TABLE_COUNT, tableUnlock } from "./data.js?v=040ed05b";
import { GOAL_ALL_TABLES, SkipBoSession, Stats, resultText } from "./session.js?v=040ed05b";

/** Free play is the printed game: every table open, four discard piles. */
const FREE_PLAY_SLOT = Object.freeze({ goal: GOAL_ALL_TABLES, checks_per_table: 3, store_slots: 0 });
const FREE_PLAY_ITEMS = [
  ...Array.from({ length: TABLE_COUNT }, (_, i) => tableUnlock(i + 1)),
  DISCARD_PILE, DISCARD_PILE,
];
const FREE_PLAY_KEY = "skipbo_free_play";

export class SkipBoClient {
  constructor({ onUpdate = () => {}, onLog = () => {}, onMessage = () => {} } = {}) {
    this.client = new Client();
    this.session = new SkipBoSession();
    this.onUpdate = onUpdate;
    this.onLog = onLog;
    this.onMessage = onMessage;
    this.connected = false;
    this.offline = false;
    this.restoreState = "needed";
    this.goalSent = false;
    this.killed = false;
    this.#listen();
  }

  // Once, in the constructor: archipelago.js never drops a listener, so
  // registering in connect() would stack a copy per reconnect.
  #listen() {
    this.client.items.on("itemsReceived", () => this.syncItems());
    this.client.messages.on("message", (text, nodes) => this.onMessage(text, nodes));
    this.client.deathLink.on("deathReceived", (source, _time, cause) => {
      if (!this.connected || !this.session.deathLink) return;
      this.onLog(`DeathLink from ${source}${cause ? `: ${cause}` : ""}`);
      if (!this.session.table || this.session.gameOver) {
        this.onLog("No game in progress, so nothing to lose.");
        return;
      }
      this.killed = true;
      this.session.forfeit();
      this.afterAction();
    });
    this.client.socket.on("disconnected", () => {
      this.connected = false;
      this.onLog("Disconnected.");
      this.onUpdate();
    });
  }

  #self() {
    try {
      return this.client.players.self ?? null;
    } catch {
      return null;
    }
  }

  get saveKey() {
    const self = this.#self();
    return `skipbo_game_${self?.team ?? 0}_${self?.slot ?? 0}`;
  }

  // -- free play -------------------------------------------------------------
  startFreePlay({ fresh = false } = {}) {
    this.connected = false;
    this.offline = true;
    this.goalSent = false;
    this.session = new SkipBoSession(FREE_PLAY_SLOT);
    this.session.setItems(FREE_PLAY_ITEMS);
    this.session.autoStock = this.autoStockPref;
    if (fresh) this.#writeLocal(null);
    const stored = this.#readLocal();
    if (stored && stored.gamesPlayed) {
      this.session.stats = stored;
      this.onLog(`Free play: restored ${stored.gamesPlayed} game(s), ${stored.gamesWon} won.`);
    } else {
      this.onLog("Free play -- no server. Every table is open; pick one.");
    }
    this.restoreState = "done";
    this.onUpdate();
  }

  #writeLocal(payload) {
    try {
      if (payload === null) localStorage.removeItem(FREE_PLAY_KEY);
      else localStorage.setItem(FREE_PLAY_KEY, JSON.stringify(payload));
    } catch { /* storage refused (private window): play on */ }
  }

  #readLocal() {
    try {
      const raw = localStorage.getItem(FREE_PLAY_KEY);
      return raw === null ? null : Stats.fromPayload(JSON.parse(raw));
    } catch {
      return null;
    }
  }

  // -- connection ------------------------------------------------------------
  async connect(url, slotName, password = "") {
    // Omit the key when there is no password: archipelago.js spreads options
    // over its defaults, and `password: undefined` hangs the login.
    const options = {};
    if (password) options.password = password;
    const slotData = await this.client.login(url, slotName, GAME_NAME, options);
    this.offline = false;
    this.session = new SkipBoSession(slotData);
    this.session.autoStock = this.autoStockPref;
    this.session.reported = new Set(this.client.room.checkedLocations);
    this.goalSent = false;
    this.restoreState = "needed";
    if (this.session.deathLink) this.client.deathLink.enableDeathLink();
    // Before `connected`, so the starting items are not announced as news.
    this.syncItems();
    this.connected = true;
    await this.restore();
    this.onLog(`Connected as ${slotName}.`);
    this.afterAction();
    return slotData;
  }

  syncItems() {
    const before = this.session.unlockedTables;
    this.session.setItems(this.client.items.received.map((item) => item.name));
    if (this.connected) {
      for (const t of this.session.unlockedTables) if (!before.has(t)) this.onLog(`Table ${t} unlocked.`);
    }
    this.onUpdate();
  }

  async restore() {
    this.restoreState = "requested";
    try {
      const stats = Stats.fromPayload(await this.client.storage.fetch(this.saveKey));
      if (stats) {
        this.session.stats = stats;
        this.onLog(`Restored ${stats.gamesPlayed} game(s), ${stats.gamesWon} won.`);
      }
    } catch (err) {
      this.onLog(`Could not read the saved stats: ${err.message}`);
    }
    this.restoreState = "done";
  }

  async save() {
    if (this.restoreState !== "done") return;
    const payload = this.session.stats.toPayload();
    if (this.offline) {
      this.#writeLocal(payload);
      return;
    }
    if (!this.connected) return;
    try {
      await this.client.storage.prepare(this.saveKey, {}).replace(payload).commit();
    } catch (err) {
      this.onLog(`Could not save: ${err.message}`);
    }
  }

  // -- after every action ----------------------------------------------------
  /** Settle a finished game, send new checks, save, and trip the goal. */
  afterAction() {
    const s = this.session;
    let changed = false;
    if (s.gameOver && !s.lastResult) {
      const result = s.settle();
      this.onLog(resultText(result));
      changed = true;
      if (!result.won && this.connected && s.deathLink && !this.killed) {
        const name = this.#self()?.name ?? "A player";
        this.client.deathLink.sendDeathLink(name, "lost at Skip-Bo");
        this.onLog("DeathLink sent.");
      }
      this.killed = false;
    }
    if (this.restoreState === "done" && !this.offline) {
      const fresh = s.newChecks();
      if (fresh.length && this.connected) {
        this.client.check(...fresh);
        changed = true;
      }
    }
    if (changed) this.save();
    if (s.goalMet && !this.goalSent && this.connected) {
      this.client.goal();
      this.goalSent = true;
      this.onLog("Goal complete!");
    }
    this.onUpdate();
  }

  buy(slot) {
    const id = this.session.buy(slot);
    this.afterAction();
    return id;
  }

  /** The player's Auto-stock choice, kept across games and reconnects. */
  get autoStockPref() {
    try {
      return localStorage.getItem("skipbo_auto_stock") === "1";
    } catch {
      return false;
    }
  }

  setAutoStock(on) {
    this.session.autoStock = on;
    try {
      localStorage.setItem("skipbo_auto_stock", on ? "1" : "0");
    } catch { /* fine */ }
    if (on && this.session.myTurn) this.session.afterHumanAction();
    this.afterAction();
  }
}
