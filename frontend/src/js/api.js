// Small fetch wrapper for /api/v1. The helper key lives only in this tab's sessionStorage.

const BASE = "/api/v1";
const KEY_NAME = "rvb.helperKey";

export const helperKey = {
  get: () => {
    try {
      return sessionStorage.getItem(KEY_NAME) || "";
    } catch {
      return "";
    }
  },
  set: (k) => {
    try {
      sessionStorage.setItem(KEY_NAME, k);
    } catch {
      /* private mode: key lasts until reload */
    }
  },
  clear: () => {
    try {
      sessionStorage.removeItem(KEY_NAME);
    } catch {
      /* ignore */
    }
  },
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : detail?.message || `Request failed (${status})`);
    this.status = status;
    this.code = typeof detail === "object" ? detail?.code : undefined;
  }
}

async function request(path, { method = "GET", body, admin = false, raw = false } = {}) {
  const headers = {};
  if (admin) headers["X-RVB-Key"] = helperKey.get();
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, { method, headers, body, credentials: "same-origin" });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  if (raw) return res.blob();
  return res.status === 204 ? null : res.json();
}

const audioForm = (wavBytes, fields = {}) => {
  const fd = new FormData();
  fd.append("audio", new Blob([wavBytes], { type: "audio/wav" }), "take.wav");
  for (const [k, v] of Object.entries(fields)) fd.append(k, v ?? "");
  return fd;
};

export const api = {
  phrases: () => request("/phrases"),
  checkKey: () => request("/auth/check", { admin: true }),
  interpret: (wav) => request("/interpret", { method: "POST", body: audioForm(wav) }),
  addTake: (wav, fields) => request("/takes", { method: "POST", body: audioForm(wav, fields), admin: true }),
  takes: () => request("/takes", { admin: true }),
  takeAudio: (id) => request(`/takes/${encodeURIComponent(id)}/audio`, { admin: true, raw: true }),
  deleteTake: (id) => request(`/takes/${encodeURIComponent(id)}`, { method: "DELETE", admin: true }),
  deleteBySpeaker: (speaker) => request(`/takes?speaker=${encodeURIComponent(speaker)}`, { method: "DELETE", admin: true }),
  addPhrase: (english, category) => request("/phrases", { method: "POST", body: { english, category }, admin: true }),
  exportZip: () => request("/export", { admin: true, raw: true }),
};
