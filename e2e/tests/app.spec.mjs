import { expect, test } from "@playwright/test";

const KEY = process.env.RVB_E2E_KEY;

test.beforeEach(async ({ page }) => {
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && page.errors.push(m.text()));
});

test.afterEach(async ({ page }) => {
  // Catches CSP violations and script errors.
  expect(page.errors).toEqual([]);
});

test("speak page loads with no Rohingya text inputs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Rohingya Voice Interpreter" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tap to speak" })).toBeVisible();
  await expect(page.locator("#view-speak input, #view-speak textarea")).toHaveCount(0);
});

test("wrong helper key stays locked", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /Teach/ }).click();
  page.once("dialog", (d) => d.dismiss());
  await page.getByPlaceholder("Helper key").fill("wrong");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.locator("#teach-list")).toBeHidden();
  page.errors = page.errors.filter((e) => !e.includes("401")); // the failed check is expected
});

test("teach a take with the (fake) microphone, then speak", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /Teach/ }).click();
  await page.getByPlaceholder("Helper key").fill(KEY);
  await page.getByRole("button", { name: "Unlock" }).click();

  const row = page.locator(".phrase", { hasText: "Thank you." });
  await expect(row).toBeVisible();
  const rec = row.getByRole("button", { name: "● Record take" });
  await rec.click();
  await page.waitForTimeout(1500);
  await row.getByRole("button", { name: "■ Stop" }).click();
  await expect(row.locator(".msg")).toHaveText(/Saved ✓|too|Please/);

  await page.getByRole("tab", { name: /Speak/ }).click();
  await page.getByRole("button", { name: "Tap to speak" }).click();
  await page.waitForTimeout(1500);
  await page.locator("#mic").click();
  const result = page.locator("#result");
  await expect(result).toBeVisible();
  await expect(result.locator(".result-title")).not.toHaveText("Listening…");
});

test("phrases & tests: record an untaught test take, list, export, delete", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /Teach/ }).click();
  await page.getByPlaceholder("Helper key").fill(KEY);
  await page.getByRole("button", { name: "Unlock" }).click();
  await page.getByRole("tab", { name: /Phrases/ }).click();

  await page.locator("#test-speaker").fill("e2e");
  await page.locator("#test-phrase").selectOption("__untaught__");
  await page.locator("#test-note").fill("Where is the bus stop?");
  await page.getByRole("button", { name: "● Record test" }).click();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "■ Stop" }).click();
  await expect(page.locator("#test-msg")).toHaveText(/saved ✓|too|Please/);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /Download .zip/ }).click();
  expect((await download).suggestedFilename()).toBe("rvb-recordings.zip");

  await page.locator("#del-speaker").fill("e2e");
  page.on("dialog", (d) => d.accept());
  await page.locator("#del-speaker-btn").click();
  await expect(page.locator("#takes-body")).not.toContainText("Where is the bus stop?");
});
