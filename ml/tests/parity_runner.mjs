// Reads {signals: [{x, rate}]} JSON on stdin, runs frontend/src/js/dsp.js, writes results to stdout.
import { readFileSync } from "node:fs";
import { extract, quality, resampleLinear, trimBounds } from "../../frontend/src/js/dsp.js";

const input = JSON.parse(readFileSync(0, "utf8"));
const out = input.signals.map(({ x, rate }) => {
  const x16 = resampleLinear(x, rate);
  return {
    resampled: Array.from(x16),
    trim: trimBounds(x16),
    features: extract(x, rate).map((row) => Array.from(row)),
    quality: quality(x, rate),
  };
});
process.stdout.write(JSON.stringify(out));
