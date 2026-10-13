import assert from "node:assert/strict";
import { test } from "node:test";
import * as dsp from "../src/js/dsp.js";

const tone = (seconds, freq = 440, gain = 0.5, rate = 16000) =>
  Float64Array.from({ length: Math.round(seconds * rate) }, (_, i) => gain * Math.sin((2 * Math.PI * freq * i) / rate));

const withSilence = (x, pad = 8000) => {
  const out = new Float64Array(x.length + 2 * pad);
  out.set(x, pad);
  return out;
};

test("fft matches a naive DFT", () => {
  const n = 16;
  const x = Array.from({ length: n }, (_, i) => Math.sin(i) + 0.3 * Math.cos(3 * i));
  const re = Float64Array.from(x);
  const im = new Float64Array(n);
  dsp.fft(re, im);
  for (let k = 0; k < n; k++) {
    let r = 0;
    let m = 0;
    for (let t = 0; t < n; t++) {
      r += x[t] * Math.cos((-2 * Math.PI * k * t) / n);
      m += x[t] * Math.sin((-2 * Math.PI * k * t) / n);
    }
    assert.ok(Math.abs(re[k] - r) < 1e-9 && Math.abs(im[k] - m) < 1e-9);
  }
});

test("resampleLinear keeps length ratio and identity", () => {
  const x = tone(0.3, 300, 0.5, 48000);
  assert.equal(dsp.resampleLinear(x, 48000).length, 4800);
  assert.deepEqual(Array.from(dsp.resampleLinear([1, 2, 3], 16000)), [1, 2, 3]);
});

test("trimBounds finds the tone inside silence", () => {
  const [start, end] = dsp.trimBounds(withSilence(tone(0.5)));
  assert.ok(start > 6000 && start < 8000, `start=${start}`);
  assert.ok(end > 16000 && end < 18000, `end=${end}`);
  assert.deepEqual(dsp.trimBounds(new Float64Array(8000)), [0, 0]);
});

test("filterbank and DCT shapes", () => {
  const fb = dsp.melFilterbank();
  assert.equal(fb.length, 26);
  assert.equal(fb[0].length, 257);
  assert.ok(fb.every((row) => row.some((v) => v > 0)));
  assert.equal(dsp.dctMatrix().length, 13);
});

test("extract returns normalised 26-dim frames", () => {
  const f = dsp.extract(withSilence(tone(0.6, 600)));
  assert.equal(f[0].length, dsp.FEATURE_DIM);
  assert.ok(f.length > 50 && f.length < 80);
  for (let d = 0; d < dsp.FEATURE_DIM; d++) {
    const mean = f.reduce((a, row) => a + row[d], 0) / f.length;
    assert.ok(Math.abs(mean) < 1e-9);
  }
});

test("quality flags short, quiet and loud recordings", () => {
  assert.equal(dsp.quality(withSilence(tone(0.6)), 16000).problem, null);
  assert.equal(dsp.quality(withSilence(tone(0.1)), 16000).problem, "too_short");
  assert.equal(dsp.quality(withSilence(tone(0.6, 440, 0.001)), 16000).problem, "too_quiet");
  assert.equal(dsp.quality(new Float64Array(16000), 16000).problem, "too_quiet");
  const loud = withSilence(tone(0.6, 440, 3)).map((v) => Math.max(-1, Math.min(1, v)));
  assert.equal(dsp.quality(loud, 16000).problem, "too_loud");
});
