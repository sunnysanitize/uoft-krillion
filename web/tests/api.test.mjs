import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../app/lib/api.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
});
const { api } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("a correct Dive uses one request to check and score", async (t) => {
  const calls = [];
  const result = { accepted: true, result: { valid: true, points: 30 } };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json(result);
  });
  assert.deepEqual(await api.attempt("player-aaaa", "colleges", "Vic"), result);
  assert.deepEqual(calls, [{
    url: "/api/attempt",
    body: { player_id: "player-aaaa", prompt_id: "colleges", answer: "Vic" },
  }]);
});

test("a rejected Dive does not send a guess that spends the prompt", async (t) => {
  const calls = [];
  const result = { accepted: false, check: { recognized: false, correct: false, suggestion: "Victoria College" } };
  t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(url);
    return Response.json(result);
  });
  assert.deepEqual(await api.attempt("player-aaaa", "colleges", "Vctoria"), result);
  assert.deepEqual(calls, ["/api/attempt"]);
});

test("an older backend remains playable while deployments roll out", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(url);
    if (url === "/api/attempt") return new Response(null, { status: 404 });
    if (url === "/api/check") return Response.json({ recognized: true, correct: true, suggestion: null });
    return Response.json({ valid: true, points: 10 });
  });
  assert.deepEqual(await api.attempt("player-aaaa", "colleges", "Vic"), {
    accepted: true, result: { valid: true, points: 10 },
  });
  assert.deepEqual(calls, ["/api/attempt", "/api/check", "/api/guess"]);
});

test("server errors do not trigger a second submission", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(url);
    return new Response(null, { status: 500 });
  });
  await assert.rejects(api.attempt("player-aaaa", "colleges", "Vic"), /attempt failed \(500\)/);
  assert.deepEqual(calls, ["/api/attempt"]);
});
