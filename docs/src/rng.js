// A seedable random source with the three calls the game makes:
// random(), choice(array) and shuffle(array, in place). The tests swap in a
// scripted one that replays what Python's random.Random produced.

export class Rng {
  constructor(seed = Math.floor(Math.random() * 2 ** 32)) {
    this.state = seed >>> 0;
  }

  random() {
    // mulberry32
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let t = this.state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  choice(items) {
    return items[Math.floor(this.random() * items.length)];
  }

  shuffle(items) {
    for (let i = items.length - 1; i > 0; i -= 1) {
      const j = Math.floor(this.random() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]];
    }
    return items;
  }
}
