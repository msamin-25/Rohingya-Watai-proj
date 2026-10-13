// Speech features in the browser.
//
// PARITY: this file is a line-by-line port of ml/rvb_ai/features.py (and resample_linear /
// quality from ml/rvb_ai/audio.py). If you change one, change both the same way and run
// ml/tests/test_parity.py.
//
// The app uses it to check a recording before upload (too quiet / too short / too loud), so
// the person can redo a take straight away. The server recomputes features with Python.

export const SAMPLE_RATE = 16000;
export const FRAME_LEN = 400; // 25 ms at 16 kHz
export const HOP = 160; // 10 ms
export const N_FFT = 512;
export const N_MELS = 26;
export const N_MFCC = 13;
export const PREEMPH = 0.97;
export const FMIN = 20.0;
export const FMAX = 8000.0;
export const TRIM_TOP_DB = 35.0;
export const TRIM_FLOOR_DB = -60.0;
export const TRIM_PAD_FRAMES = 5;
export const EPS = 1e-10;
export const FEATURE_DIM = 2 * N_MFCC;

export function resampleLinear(x, rateIn, rateOut = SAMPLE_RATE) {
  if (rateIn === rateOut || x.length === 0) return Float64Array.from(x);
  const nOut = Math.floor((x.length * rateOut) / rateIn + 0.5);
  const step = rateIn / rateOut;
  const out = new Float64Array(nOut);
  const last = x.length - 1;
  for (let i = 0; i < nOut; i++) {
    const t = i * step;
    if (t >= last) {
      out[i] = x[last];
    } else {
      const k = Math.floor(t);
      const frac = t - k;
      out[i] = x[k] * (1 - frac) + x[k + 1] * frac;
    }
  }
  return out;
}

function nFrames(nSamples) {
  return nSamples >= FRAME_LEN ? 1 + Math.floor((nSamples - FRAME_LEN) / HOP) : 1;
}

function frames(x) {
  let y = x;
  if (y.length < FRAME_LEN) {
    y = new Float64Array(FRAME_LEN);
    y.set(x);
  }
  const n = nFrames(y.length);
  const out = [];
  for (let f = 0; f < n; f++) out.push(y.subarray(f * HOP, f * HOP + FRAME_LEN));
  return out;
}

export function frameDb(x) {
  return frames(Float64Array.from(x)).map((fr) => {
    let s = 0;
    for (let i = 0; i < fr.length; i++) s += fr[i] * fr[i];
    return 20 * Math.log10(Math.max(Math.sqrt(s / fr.length), EPS));
  });
}

export function trimBounds(x) {
  if (x.length === 0) return [0, 0];
  const db = frameDb(x);
  const floor = Math.max(Math.max(...db) - TRIM_TOP_DB, TRIM_FLOOR_DB);
  let first = -1;
  let last = -1;
  for (let i = 0; i < db.length; i++) {
    if (db[i] > floor) {
      if (first < 0) first = i;
      last = i;
    }
  }
  if (first < 0) return [0, 0];
  const start = Math.max(0, (first - TRIM_PAD_FRAMES) * HOP);
  const end = Math.min(x.length, (last + TRIM_PAD_FRAMES) * HOP + FRAME_LEN);
  return [start, end];
}

const hzToMel = (f) => 2595 * Math.log10(1 + f / 700);
const melToHz = (m) => 700 * (10 ** (m / 2595) - 1);

export function melFilterbank() {
  const mLo = hzToMel(FMIN);
  const mHi = hzToMel(FMAX);
  const hz = [];
  // matches np.linspace(mLo, mHi, N_MELS + 2)
  for (let i = 0; i < N_MELS + 2; i++) {
    const m = i === N_MELS + 1 ? mHi : mLo + (i * (mHi - mLo)) / (N_MELS + 1);
    hz.push(melToHz(m));
  }
  const nBins = N_FFT / 2 + 1;
  const fb = [];
  for (let m = 0; m < N_MELS; m++) {
    const [lo, mid, hi] = [hz[m], hz[m + 1], hz[m + 2]];
    const row = new Float64Array(nBins);
    for (let k = 0; k < nBins; k++) {
      const f = (k * SAMPLE_RATE) / N_FFT;
      row[k] = Math.max(0, Math.min((f - lo) / (mid - lo), (hi - f) / (hi - mid)));
    }
    fb.push(row);
  }
  return fb;
}

export function dctMatrix() {
  const d = [];
  for (let k = 0; k < N_MFCC; k++) {
    const row = new Float64Array(N_MELS);
    for (let n = 0; n < N_MELS; n++) {
      row[n] = Math.sqrt(2 / N_MELS) * Math.cos((Math.PI * k * (2 * n + 1)) / (2 * N_MELS));
      if (k === 0) row[n] *= 1 / Math.sqrt(2);
    }
    d.push(row);
  }
  return d;
}

const FB = melFilterbank();
const DCT = dctMatrix();
const WINDOW = Float64Array.from({ length: FRAME_LEN }, (_, n) => 0.54 - 0.46 * Math.cos((2 * Math.PI * n) / (FRAME_LEN - 1)));

// In-place iterative radix-2 complex FFT (length must be a power of two).
export function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < len / 2; k++) {
        const wr = Math.cos(ang * k);
        const wi = Math.sin(ang * k);
        const a = i + k;
        const b = a + len / 2;
        const xr = re[b] * wr - im[b] * wi;
        const xi = re[b] * wi + im[b] * wr;
        re[b] = re[a] - xr;
        im[b] = im[a] - xi;
        re[a] += xr;
        im[a] += xi;
      }
    }
  }
}

export function mfcc(x) {
  const y = Float64Array.from(x);
  for (let i = x.length - 1; i >= 1; i--) y[i] = x[i] - PREEMPH * x[i - 1];
  const nBins = N_FFT / 2 + 1;
  return frames(y).map((fr) => {
    const re = new Float64Array(N_FFT);
    const im = new Float64Array(N_FFT);
    for (let i = 0; i < FRAME_LEN; i++) re[i] = fr[i] * WINDOW[i];
    fft(re, im);
    const power = new Float64Array(nBins);
    for (let k = 0; k < nBins; k++) power[k] = (re[k] * re[k] + im[k] * im[k]) / N_FFT;
    const logmel = FB.map((row) => {
      let s = 0;
      for (let k = 0; k < nBins; k++) s += power[k] * row[k];
      return Math.log(Math.max(s, EPS));
    });
    return Float64Array.from(DCT, (row) => row.reduce((acc, v, n) => acc + v * logmel[n], 0));
  });
}

export function deltas(c) {
  const T = c.length;
  return c.map((_, t) => {
    const next = c[Math.min(t + 1, T - 1)];
    const prev = c[Math.max(t - 1, 0)];
    return Float64Array.from(next, (v, i) => (v - prev[i]) / 2);
  });
}

export function cmvn(f) {
  const T = f.length;
  const D = f[0].length;
  const mean = new Float64Array(D);
  const std = new Float64Array(D);
  for (const row of f) for (let d = 0; d < D; d++) mean[d] += row[d] / T;
  for (const row of f) for (let d = 0; d < D; d++) std[d] += (row[d] - mean[d]) ** 2 / T;
  for (let d = 0; d < D; d++) std[d] = Math.sqrt(std[d]);
  return f.map((row) => Float64Array.from(row, (v, d) => (v - mean[d]) / (std[d] + 1e-8)));
}

export function extract(x, rate = SAMPLE_RATE) {
  let x16 = resampleLinear(x, rate);
  const [start, end] = trimBounds(x16);
  x16 = end <= start ? x16.subarray(0, FRAME_LEN) : x16.subarray(start, end);
  const c = mfcc(x16);
  const d = deltas(c);
  return cmvn(c.map((row, t) => Float64Array.from([...row, ...d[t]])));
}

// Mirrors Quality in ml/rvb_ai/audio.py.
export function quality(x, rate) {
  const x16 = resampleLinear(x, rate);
  const [start, end] = trimBounds(x16);
  const voiced = x16.subarray(start, end);
  let s = 0;
  for (let i = 0; i < voiced.length; i++) s += voiced[i] * voiced[i];
  const rms = voiced.length ? Math.sqrt(s / voiced.length) : 0;
  let clipped = 0;
  for (let i = 0; i < x.length; i++) if (Math.abs(x[i]) >= 0.999) clipped++;
  const q = {
    durationS: x.length / rate,
    voicedS: voiced.length / SAMPLE_RATE,
    rmsDb: 20 * Math.log10(Math.max(rms, EPS)),
    peakDb: x16.length ? Math.max(...frameDb(x16)) : -200,
    clippedFraction: x.length ? clipped / x.length : 0,
  };
  q.problem = qualityProblem(q);
  return q;
}

export function qualityProblem(q) {
  if (q.peakDb < -45 || q.rmsDb < -50) return "too_quiet";
  if (q.voicedS < 0.25) return "too_short";
  if (q.clippedFraction > 0.02) return "too_loud";
  return null;
}
