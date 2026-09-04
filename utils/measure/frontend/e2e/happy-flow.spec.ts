import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mockApi } from "./mock-api";

/**
 * Happy-flow smoke tests in a real browser.
 *
 * The unit suite already covers each view in jsdom; these exist for what jsdom cannot show —
 * that the shell boots, that shadow-DOM form sections really submit through the owning form,
 * and that the screens hand over to one another in order.
 */

async function startAverageSetup(page: Page): Promise<void> {
  await page.getByRole("button", { name: "New measurement" }).click();
  await page.getByRole("button", { name: /Average/ }).click();
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
});

test("boots and lists the stored measurement sessions", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Your measurements" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hue White Ambiance A60" })).toBeVisible();
  await expect(page.getByText("Completed")).toBeVisible();
  await expect(page.getByRole("button", { name: "New measurement" })).toBeEnabled();

  const measureAgain = page.getByRole("button", { name: "Measure again" });
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toBeHidden();
  await measureAgain.hover();
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toHaveText("Start a new measurement using these settings");
});

test("configures a measurement and reaches the setup check", async ({ page }) => {
  await page.getByRole("button", { name: "New measurement" }).click();
  await expect(page.getByRole("heading", { name: "Configure the measurement" })).toBeVisible();

  await page.getByRole("button", { name: /Average/ }).click();

  // The power meter comes from settings rather than the form, and is restated here.
  await expect(page.getByText("Plug power · sensor.plug_power")).toBeVisible();
  await expect(page.getByText("Measurement device: Shelly Plug S")).toBeVisible();

  await page.getByLabel("Duration (seconds)").fill("60");
  await page.getByRole("button", { name: "Check setup" }).click();

  await expect(page.getByRole("heading", { name: "Ready for the bench" })).toBeVisible();
  await expect(page.getByText("Measurement device quality")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start measurement" })).toBeEnabled();
});

test("searches and selects a Home Assistant light with the shared combobox", async ({ page }) => {
  await page.getByRole("button", { name: "New measurement" }).click();
  await page.getByRole("button", { name: /Light bulb/ }).click();

  const light = page.getByRole("combobox", { name: "Light" });
  await light.fill("desk");
  await expect(page.getByRole("listbox", { name: "Light options" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Desk lamp · light.desk" })).toBeVisible();
  await light.press("ArrowDown");
  await light.press("Enter");

  await expect(light).toHaveValue("Desk lamp · light.desk");
  await expect(page.getByRole("listbox", { name: "Light options" })).toBeHidden();
});

test("starts the measurement and shows live events on the running screen", async ({ page }) => {
  await startAverageSetup(page);
  await page.getByRole("button", { name: "Check setup" }).click();
  await page.getByRole("button", { name: "Start measurement" }).click();

  await expect(page.getByText("Measuring average power")).toBeVisible();

  // The log drawer only exists once a log event has arrived, and its contents come from
  // nowhere else, so both prove the SSE stream was decoded. Connection state is deliberately
  // not asserted: the mocked stream is one response body, reported closed once replayed.
  await page.getByRole("button", { name: /View log/ }).click();
  await expect(page.getByText("Connected to the power meter")).toBeVisible();
});

test("opens a completed session and shows its result artifacts", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Measurement complete" })).toBeVisible();
  await expect(page.getByText("8.42 W")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Generated files" })).toBeVisible();
  // Located by download link: the plot header repeats the source file name as plain text.
  await expect(page.getByRole("link", { name: "Download brightness.csv" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download model.json" })).toBeVisible();
});

test("opens settings from setup with the configured power meter", async ({ page }) => {
  await startAverageSetup(page);
  await page.getByRole("button", { name: "Change power meter" }).click();

  await expect(page.getByRole("heading", { name: "Measurement defaults" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Measurement device name" })).toHaveValue("Shelly Plug S");
  await expect(page.getByLabel("Type")).toHaveValue("hass");
  await expect(page.getByRole("combobox", { name: "Power sensor" })).toHaveValue("Plug power · sensor.plug_power");

  const deviceName = page.getByRole("combobox", { name: "Measurement device name" });
  await deviceName.fill("plus");
  await expect(page.getByRole("listbox", { name: "Measurement device name options" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Shelly Plus Plug S" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Aeotec ZWA023" })).toBeHidden();
  await deviceName.press("ArrowDown");
  await deviceName.press("Enter");
  await expect(deviceName).toHaveValue("Shelly Plus Plug S");
  await expect(page.getByRole("listbox", { name: "Measurement device name options" })).toBeHidden();
});
