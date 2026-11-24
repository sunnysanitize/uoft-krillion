import assert from "node:assert/strict";
import { test } from "node:test";
import React, { act } from "react";
import { create } from "react-test-renderer";
import { loadTs } from "./helpers/load-ts.mjs";

const { api } = loadTs(new URL("../app/lib/api.ts", import.meta.url));
const { useDive } = loadTs(new URL("../app/lib/useDive.ts", import.meta.url));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const play = {
  answers: [{ names: ["Victoria College", "vic"], points: 30, share_pct: 5, rarity: "Uncommon", golden: false }],
  decoys: ["Massey College"], golden_answer: "Victoria College", top: [], deep_cuts: [], players: 0, valid_answers: 1,
};
const daily = {
  day: "2026-11-23", number: 23, time_limit: 25, meters_per_point: 10,
  zones: [{ start: 0, name: "Shallows" }],
  prompts: ["first", "second"].map((id) => ({ id, text: "Name a college", hint: "", play })),
};
const confirmed = {
  valid: true, answer: "Victoria College", points: 30, share_pct: 5, rarity: "Uncommon", golden: false,
  golden_answer: "Victoria College", top: [], deep_cuts: [], players: 1, valid_answers: 1,
};

async function mount(t, { stored, data = daily, guess } = {}) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: new Date("2026-11-23T20:00:00Z") });
  const values = new Map(stored ? [[`rb:dive:${data.day}`, JSON.stringify(stored)]] : []);
  const original = new Map(["localStorage", "addEventListener", "removeEventListener"].map((key) => [key, globalThis[key]]));
  globalThis.localStorage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  t.mock.method(api, "daily", async () => data);
  t.mock.method(api, "attempt", () => { throw new Error("preloaded answers must not be checked over the network"); });
  const save = t.mock.method(api, "guess", guess ?? (async () => confirmed));
  const finish = t.mock.method(api, "finish", async () => ({ score: 30, percentile: 100, players: 1 }));
  t.mock.method(api, "leaderboard", async () => ({ players: [] }));
  let game;
  function Harness() { game = useDive(); return null; }
  let renderer;
  await act(async () => { renderer = create(React.createElement(Harness)); });
  t.after(async () => {
    await act(async () => renderer.unmount());
    for (const [key, value] of original) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  });
  return { game: () => game, save, finish, values };
}

test("Dive starts the scored animation before a pending save resolves, and prevents double clicks", async (t) => {
  let resolveSave;
  const pending = new Promise((resolve) => { resolveSave = resolve; });
  const app = await mount(t, { guess: () => pending });
  await act(async () => app.game().begin());
  await act(async () => {
    app.game().submit("vic");
    app.game().submit("vic");
  });
  assert.equal(app.game().phase, "flash");
  assert.equal(app.game().submitting, false);
  assert.equal(app.game().results.length, 1);
  assert.equal(app.game().results[0].points, 30);
  assert.equal(app.game().results[0].synced, false);
  assert.equal(app.save.mock.callCount(), 1);
  await act(async () => t.mock.timers.tick(4000));
  assert.equal(app.game().phase, "play");
  assert.equal(app.game().idx, 1);
  const remaining = app.game().remaining;
  await act(async () => resolveSave(confirmed));
  assert.equal(app.game().results[0].synced, true);
  assert.equal(app.game().remaining, remaining);
  assert.equal(app.game().idx, 1);
});

test("wrong answers and suggestions are immediate and never spend or save the prompt", async (t) => {
  const app = await mount(t);
  await act(async () => app.game().begin());
  let check;
  await act(async () => { check = await app.game().submit("Massey College"); });
  assert.deepEqual(check, { recognized: true, correct: false, suggestion: null });
  await act(async () => { check = await app.game().submit("Vctoria"); });
  assert.equal(check.suggestion, "Victoria College");
  assert.equal(app.game().phase, "play");
  assert.equal(app.game().results.length, 0);
  assert.equal(app.save.mock.callCount(), 0);
});

test("a failed background save does not interrupt play and finish waits for retry", async (t) => {
  let failed = true;
  const app = await mount(t, {
    data: { ...daily, prompts: daily.prompts.slice(0, 1) },
    guess: async () => { if (failed) throw new Error("offline"); return confirmed; },
  });
  await act(async () => app.game().begin());
  await act(async () => app.game().submit("vic"));
  assert.equal(app.game().phase, "flash");
  assert.equal(app.game().sonarLost, true);
  await act(async () => t.mock.timers.tick(4000));
  assert.equal(app.game().phase, "done");
  assert.equal(app.finish.mock.callCount(), 0);
  failed = false;
  await act(async () => app.game().retrySonar());
  assert.equal(app.game().results[0].synced, true);
  assert.equal(app.save.mock.callCount(), 2);
  assert.equal(app.finish.mock.callCount(), 1);
  assert.equal(app.game().finish.score, 30);
});

test("refresh restores unsent guesses and retries them without replaying the completed prompt", async (t) => {
  const app = await mount(t, { stored: { results: [{ ...confirmed, raw: "vic", synced: false }], startedAt: null, nickname: "Diver" } });
  assert.equal(app.game().phase, "play");
  assert.equal(app.game().idx, 1);
  assert.equal(app.game().results[0].synced, true);
  assert.equal(app.save.mock.callCount(), 1);
  assert.equal(app.save.mock.calls[0].arguments[1], "first");
});

test("a confirmation received during the animation survives the next prompt transition", async (t) => {
  const app = await mount(t);
  await act(async () => app.game().begin());
  await act(async () => app.game().submit("vic"));
  assert.equal(app.game().results[0].synced, true);
  await act(async () => t.mock.timers.tick(4000));
  assert.equal(app.game().phase, "play");
  assert.equal(app.game().results[0].synced, true);
  assert.equal(app.save.mock.callCount(), 1);
});

test("running out of air animates a miss locally without waiting for the server", async (t) => {
  const app = await mount(t, { guess: () => new Promise(() => {}) });
  await act(async () => app.game().begin());
  await act(async () => app.game().submit("", true));
  assert.equal(app.game().phase, "flash");
  assert.equal(app.game().results[0].valid, false);
  assert.equal(app.game().results[0].points, 0);
  assert.equal(app.save.mock.calls[0].arguments[2], "");
});
