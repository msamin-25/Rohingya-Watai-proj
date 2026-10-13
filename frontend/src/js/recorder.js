// Microphone recording -> 16 kHz mono WAV bytes. Works on http://localhost (a secure context).
import { SAMPLE_RATE, quality } from "./dsp.js";
import { encodeWav } from "./wav.js";

export const MAX_SECONDS = 8;

export function micAvailable() {
  return Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
}

// Start recording. Returns { stop(): Promise<{wav, quality}>, cancel() }. Auto-stops after MAX_SECONDS.
export async function startRecording({ onTick } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const rec = new MediaRecorder(stream);
  const chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const started = performance.now();
  const timer = setInterval(() => {
    const s = (performance.now() - started) / 1000;
    onTick?.(s);
    if (s >= MAX_SECONDS + 1) stopNow(); // backstop; the UI normally stops at MAX_SECONDS
  }, 100);
  const done = new Promise((resolve) => (rec.onstop = resolve));
  const release = () => {
    clearInterval(timer);
    stream.getTracks().forEach((t) => t.stop());
  };
  function stopNow() {
    if (rec.state !== "inactive") rec.stop();
  }
  rec.start();

  return {
    async stop() {
      stopNow();
      await done;
      release();
      const blob = new Blob(chunks, { type: rec.mimeType });
      // Decoding into a 16 kHz context lets the browser resample with a proper filter.
      const ctx = new OfflineAudioContext(1, 1, SAMPLE_RATE);
      const audio = await ctx.decodeAudioData(await blob.arrayBuffer());
      const mono = mixToMono(audio);
      return { wav: encodeWav(mono, audio.sampleRate), quality: quality(mono, audio.sampleRate) };
    },
    cancel() {
      stopNow();
      release();
    },
  };
}

function mixToMono(buf) {
  const out = new Float32Array(buf.length);
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const ch = buf.getChannelData(c);
    for (let i = 0; i < ch.length; i++) out[i] += ch[i] / buf.numberOfChannels;
  }
  return out;
}
