// Hands back exactly the random results Python recorded (see
// tools/export_traces.py), and fails loudly the moment JS asks for a
// different kind of call than Python made.

export class ScriptedRng {
  constructor(log) {
    this.log = log;
    this.at = 0;
  }

  next(kind) {
    const entry = this.log[this.at];
    if (!entry || entry[0] !== kind) {
      throw new Error(`rng call ${this.at}: JS asked for ${kind}, Python made ${entry?.[0] ?? "no call"}`);
    }
    this.at += 1;
    return entry[1];
  }

  random() { return this.next("r"); }

  choice(items) { return items[this.next("c")]; }

  shuffle(items) {
    const order = this.next("s");
    const a = [...items].sort((x, y) => x - y).join();
    const b = [...order].sort((x, y) => x - y).join();
    if (a !== b) throw new Error("shuffle was handed different cards than Python shuffled");
    items.splice(0, items.length, ...order);
    return items;
  }
}
