// Starts the real backend on a spare port with a throwaway data folder and a random helper key,
// then drives Chromium with a fake microphone (a test tone). No real voice data is involved.
import { defineConfig, devices } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PORT = 8011;
process.env.RVB_E2E_KEY ??= randomBytes(32).toString("base64url");
process.env.RVB_E2E_DATA ??= mkdtempSync(join(tmpdir(), "rvb-e2e-"));
const python = process.platform === "win32" ? "..\\.venv\\Scripts\\python" : "../.venv/bin/python";

export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    ...devices["Desktop Chrome"],
    permissions: ["microphone"],
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
  },
  webServer: {
    command: `${python} -m uvicorn app.main:factory --factory --port ${PORT}`,
    cwd: "../backend",
    url: `http://localhost:${PORT}/api/v1/health`,
    reuseExistingServer: false,
    env: { RVB_ADMIN_TOKEN: process.env.RVB_E2E_KEY, RVB_DATA_DIR: process.env.RVB_E2E_DATA },
  },
});
