import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { describeResult } from "../src/js/messages.js";
import { encodeWav } from "../src/js/wav.js";

test("encodeWav writes a valid 16-bit mono header and clips", () => {
  const bytes = encodeWav(Float32Array.from([0, 0.5, -1, 2]), 16000);
  const v = new DataView(bytes.buffer);
  const text = (o) => String.fromCharCode(...bytes.slice(o, o + 4));
  assert.equal(text(0), "RIFF");
  assert.equal(text(8), "WAVE");
  assert.equal(v.getUint16(22, true), 1);
  assert.equal(v.getUint32(24, true), 16000);
  assert.equal(v.getUint16(34, true), 16);
  assert.equal(v.getUint32(40, true), 8);
  assert.deepEqual([0, 1, 2, 3].map((i) => v.getInt16(44 + 2 * i, true)), [0, 16384, -32768, 32767]);
});

test("only a match shows and speaks English", () => {
  const m = describeResult({ status: "match", english: "I need water.", category: "general" });
  assert.equal(m.title, "I need water.");
  assert.equal(m.speak, "I need water.");
  for (const status of ["unsure", "interpreter_needed", "no_phrases", "too_quiet", "too_short", "too_loud", "error", undefined]) {
    const r = describeResult({ status, english: "SHOULD NOT SHOW", category: "health" });
    assert.equal(r.speak, null, status);
    assert.ok(!r.title.includes("SHOULD NOT SHOW") && !r.body.includes("SHOULD NOT SHOW"), status);
  }
});

test("sensitive results send people to a human interpreter or 911", () => {
  assert.match(describeResult({ status: "interpreter_needed", category: "health" }).body, /human interpreter/);
  assert.match(describeResult({ status: "interpreter_needed", category: "legal" }).title, /legal/);
  assert.match(describeResult({ status: "interpreter_needed", category: "emergency" }).body, /911/);
  assert.match(describeResult({ status: "unsure" }).body, /human interpreter/);
});

test("the UI never asks anyone to type or read Rohingya", async () => {
  const html = await readFile(new URL("../src/index.html", import.meta.url), "utf8");
  const inputs = html.match(/<(input|textarea)[^>]*>/g) ?? [];
  for (const tag of inputs) assert.doesNotMatch(tag, /rohingya/i, tag);
  assert.doesNotMatch(html, /<textarea/);
});
