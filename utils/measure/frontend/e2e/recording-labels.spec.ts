import { expect, test } from "@playwright/test";
import { completedSession, completedSnapshot, mockApi, parameters } from "./mock-api";
import type { SessionFile, SessionSnapshot } from "../src/types";

test("saves recording labels and keeps them after reopening the session", async ({ page }, testInfo) => {
  const session = { ...completedSession, measure_type: "recorder" as const, model_id: "", product_name: "Robot vacuum", file_count: 3 };
  const snapshot: SessionSnapshot = {
    ...completedSnapshot, can_analyse: true, mode: "Recording",
    summary: { "Samples recorded": "12480", "Recordings analysed": "3" },
    request: { measure_type: "recorder", recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot", model_id: "", product_name: "Robot vacuum", measure_device: "Shelly Plug S", generate_model: true, parameters, resume_policy: "new", power_meter: { type: "dummy" } },
  };
  let files: SessionFile[] = [
    { name: "record-1.jsonl", size: 1398420, media_type: "application/octet-stream", modified_at: "2026-10-19T15:42:00Z", recording_label: "Full cleaning cycle" },
    { name: "record-2.jsonl", size: 2895100, media_type: "application/octet-stream", modified_at: "2026-10-20T07:10:00Z", recording_label: "Overnight standby" },
    { name: "record.jsonl", size: 1146320, media_type: "application/octet-stream", modified_at: "2026-10-20T10:15:00Z", recording_label: "" },
  ];
  await mockApi(page, { sessions: [session], capabilities: { runtime_version: "v0.13.1:app" } });
  await page.route("**/api/sessions/session-completed", (route) => route.fulfill({ json: snapshot }));
  await page.route("**/api/sessions/session-completed/files", (route) => route.fulfill({ json: files }));
  await page.route("**/api/sessions/session-completed/recording-label", async (route) => {
    const body = route.request().postDataJSON() as { name: string; label: string };
    expect(route.request().method()).toBe("PUT");
    files = files.map((file) => file.name === body.name ? { ...file, recording_label: body.label } : file);
    await route.fulfill({ json: files });
  });
  await page.route("**/api/sessions/session-completed/plots", (route) => route.fulfill({ json: { partial: false, plots: [], warnings: [] } }));
  await page.setViewportSize({ width: 1360, height: 1100 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Add label for record.jsonl", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Recording label", exact: true });
  await expect(input).toBeFocused();
  await input.fill("Second cleaning cycle");
  await page.screenshot({ path: testInfo.outputPath("recording-labels-edit.png"), fullPage: true });
  await page.getByRole("region", { name: "Saved files" }).screenshot({ path: testInfo.outputPath("recording-labels-editor-detail.png") });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator(".recording-label").filter({ hasText: "Second cleaning cycle" })).toBeVisible();
  await page.getByRole("button", { name: "All sessions", exact: true }).first().click();
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.locator(".recording-label").filter({ hasText: "Second cleaning cycle" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("recording-labels-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: testInfo.outputPath("recording-labels-mobile.png"), fullPage: true });
});
