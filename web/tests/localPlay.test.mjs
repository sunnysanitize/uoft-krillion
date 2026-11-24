import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { loadTs } from "./helpers/load-ts.mjs";

const { localAttempt, normalize } = loadTs(new URL("../app/lib/localPlay.ts", import.meta.url));
const fixture = JSON.parse(await readFile(new URL("../../src/tests/fixtures/local_matching.json", import.meta.url), "utf8"));
const play = {
  answers: fixture.prompt.answers.map((names) => ({ names, points: 30, share_pct: 5, rarity: "Uncommon", golden: names[0] === fixture.prompt.golden })),
  decoys: fixture.prompt.decoys, golden_answer: fixture.prompt.golden,
  top: [], deep_cuts: [], players: 0, valid_answers: fixture.prompt.answers.length,
};

test("local matching agrees with the Python server on aliases, typos, codes and ambiguous prefixes", () => {
  for (const item of fixture.cases) {
    assert.equal(normalize(item.raw), item.normalized, item.raw);
    const result = localAttempt(play, item.raw);
    assert.equal(result.accepted, item.check.correct, item.raw);
    if (result.accepted) assert.equal(result.result.answer, item.answer, item.raw);
    else assert.deepEqual(result.check, item.check, item.raw);
    assert.equal(localAttempt(play, item.raw, true).result.answer, item.answer, `timeout: ${item.raw}`);
  }
});

test("the full scored result is available synchronously without fetching", (t) => {
  t.mock.method(globalThis, "fetch", () => { throw new Error("local matching must not fetch"); });
  const result = localAttempt(play, "Vic");
  assert.equal(result.accepted, true);
  assert.equal(result.result.points, 30);
  assert.equal(result.result.rarity, "Uncommon");
  assert.equal(localAttempt(play, "", true).result.valid, false);
});
