import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mockApi, parameters, startedSnapshot } from "./mock-api";
import type { SessionSnapshot } from "../src/types";

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

test("selects a Home Assistant light with the shared combobox", async ({ page }) => {
  await page.getByRole("button", { name: "New measurement" }).click();
  await page.getByRole("button", { name: /Light bulb/ }).click();

  const light = page.getByRole("combobox", { name: "Light" });
  await light.click();
  await expect(page.getByRole("listbox", { name: "Light options" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Desk lamp · light.desk" })).toBeVisible();
  await page.getByRole("option", { name: "Desk lamp · light.desk" }).click();

  await expect(light).toHaveValue("Desk lamp · light.desk");
  await expect(page.getByRole("listbox", { name: "Light options" })).toBeHidden();
  await expect(page.locator('input[name="model_id"]')).toHaveCount(0);
  await expect(page.locator('input[name="product_name"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Check light and setup", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ready for the bench" })).toBeVisible();
  await expect(page.getByText("Desk lamp", { exact: true })).toBeVisible();
});

for (const width of [1280, 390]) {
  test(`keeps light setup compact and reveals contextual help at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole("button", { name: "New measurement" }).click();
    await page.getByRole("button", { name: /Light bulb/ }).click();

    const setup = page.locator("measure-setup-view");
    const light = setup.locator('measure-combobox[name="light_entity_id"]');
    const grid = setup.locator(".profile-grid");
    const lightBounds = await light.boundingBox();
    const gridBounds = await grid.boundingBox();
    expect(lightBounds).not.toBeNull();
    expect(gridBounds).not.toBeNull();
    expect(Math.abs(lightBounds!.width - gridBounds!.width)).toBeLessThan(1);
    await expect(setup.locator("fieldset.section")).toHaveCount(0);
    await expect(setup.getByRole("button", { name: "Change power meter" })).toBeVisible();
    await expect(setup.locator(".discovery-help p")).toBeHidden();
    await expect(setup.locator(".multiple-lights p")).toHaveCount(0);
    await expect(setup.getByRole("group", { name: "What do you want to measure?" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: testInfo.outputPath("setup.png"), fullPage: true });

    await setup.getByText("Light not found?", { exact: true }).click();
    await expect(setup.locator(".discovery-help p")).toBeVisible();
    await setup.getByText("Light not found?", { exact: true }).click();
    await setup.getByLabel("Measure multiple lights", { exact: true }).check();
    await expect(setup.locator(".multiple-lights p")).toBeVisible();
    await expect(setup.getByRole("link", { name: "Home Assistant light group" })).toBeVisible();
    await setup.getByLabel("Measure multiple lights", { exact: true }).uncheck();
    await expect(setup.locator(".multiple-lights p")).toHaveCount(0);
  });
}

test("keeps developer controls collapsed but virtual measurement status visible", async ({ page }) => {
  await mockApi(page, { capabilities: { developer_mode: true, fast_test_mode: true } });
  await page.reload();
  await page.getByRole("button", { name: "New measurement" }).click();
  await page.getByRole("button", { name: /Light bulb/ }).click();
  const setup = page.locator("measure-setup-view");
  const virtual = setup.getByLabel("Use virtual device (developer)");
  await expect(virtual).toBeHidden();
  await expect(setup.getByText("Fast test mode is enabled.")).toBeHidden();
  await setup.getByText("Developer options", { exact: true }).click();
  await expect(setup.getByText("Fast test mode is enabled.")).toBeVisible();
  await virtual.check();
  await expect(setup.getByRole("combobox", { name: "Light", exact: true })).toHaveCount(0);
  await setup.getByText("Developer options", { exact: true }).click();
  await expect(setup.getByText("Virtual device · test output only")).toBeVisible();
  await setup.getByRole("button", { name: "Check setup", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ready for the bench" })).toBeVisible();
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

test("offers a graceful stop for average measurements", async ({ page }) => {
  await page.route("**/api/sessions/session-running/cancel", async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({ json: { ...startedSnapshot, state: "cancelling", phase: "Stopping measurement" } });
  });
  await startAverageSetup(page);
  const steps = page.getByRole("navigation", { name: "Measurement progress" }).getByRole("listitem");
  await expect(steps).toHaveCount(4);
  await page.getByRole("button", { name: "Check setup" }).click();
  await expect(steps).toHaveCount(4);
  await page.getByRole("button", { name: "Start measurement" }).click();
  await expect(steps).toHaveCount(4);
  await expect(page.getByRole("button", { name: "Cancel measurement" })).toHaveCount(0);
  await page.getByRole("button", { name: "Stop measurement", exact: true }).click();
  await expect(page.getByRole("button", { name: "Stopping…", exact: true })).toBeDisabled();
});

test("ends a reopened average session at Result without profile preparation", async ({ page }) => {
  const snapshot: SessionSnapshot = {
    session_id: "session-completed", state: "completed", phase: "Measurement complete", mode: "Averaging",
    summary: { "Average power": "4.2 W", Duration: "6.5 s" },
    request: {
      measure_type: "average", duration: 60, model_id: "", product_name: "", measure_device: "Test meter",
      generate_model: false, parameters, resume_policy: "new", power_meter: { type: "dummy" },
    },
  };
  await page.route("**/api/sessions/session-completed", (route) => route.fulfill({ json: snapshot }));
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Measurement complete" })).toBeVisible();
  await expect(page.getByText("4.2 W", { exact: true })).toBeVisible();
  const steps = page.getByRole("navigation", { name: "Measurement progress" }).getByRole("listitem");
  await expect(steps).toHaveCount(4);
  await expect(steps.last()).toHaveAttribute("aria-current", "step");
  await expect(page.getByRole("button", { name: /Prepare profile/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New measurement", exact: true })).toBeVisible();
});

test("scrolls to the top when moving from result to profile preparation", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();
  const prepare = page.getByRole("button", { name: "Prepare profile" });
  await prepare.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await prepare.click();
  await expect(page.getByRole("heading", { name: "Prepare your Powercalc profile" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});

for (const width of [1280, 390]) {
  test(`aligns the contribution confirmation checkbox with its label at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route("**/api/contribution/auth", (route) => route.fulfill({ json: { connected: true, identity: { login: "tester" } } }));
    await page.getByRole("button", { name: "Open", exact: true }).click();
    await page.getByRole("button", { name: "Prepare profile" }).click();
    await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
    await page.getByRole("button", { name: "Continue to use profile" }).click();
    const row = page.locator(".confirm-row");
    await row.scrollIntoViewIfNeeded();
    const checkbox = row.getByRole("checkbox");
    const text = row.locator("span");
    const checkboxBounds = await checkbox.boundingBox();
    const textBounds = await text.boundingBox();
    expect(checkboxBounds).not.toBeNull();
    expect(textBounds).not.toBeNull();
    expect(checkboxBounds!.height).toBeLessThanOrEqual(20);
    expect(Math.abs(checkboxBounds!.y - textBounds!.y)).toBeLessThan(4);
    expect(textBounds!.x).toBeGreaterThan(checkboxBounds!.x + checkboxBounds!.width);
    await expect(page.getByRole("button", { name: "Confirm and open PR" })).toBeDisabled();
    await text.click();
    await expect(checkbox).toBeChecked();
    await expect(page.getByRole("button", { name: "Confirm and open PR" })).toBeEnabled();
    await row.screenshot({ path: testInfo.outputPath("contribution-confirmation.png") });
  });
}

test("preserves unfinished profile fields and tags when navigating back to Result", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const product = page.locator('input[name="product_name"]');
  const aliases = page.locator('input[name="aliases"]');
  const meter = page.getByRole("combobox", { name: "Measurement device", exact: true });
  await product.fill("Edited lamp ");
  await aliases.fill("Alias one, ");
  await meter.fill("Custom meter");
  await page.getByRole("combobox", { name: "Connectivity", exact: true }).click();
  await page.getByRole("option", { name: "Zigbee", exact: true }).click();
  await page.getByRole("button", { name: "Back to result", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();

  await expect(product).toHaveValue("Edited lamp ");
  await expect(aliases).toHaveValue("Alias one, ");
  await expect(meter).toHaveValue("Custom meter");
  await expect(page.getByRole("button", { name: "Remove Zigbee" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue to use profile" })).toBeHidden();
  await page.getByRole("button", { name: "Validate changes" }).click();
  await expect(page.locator(".validation-status")).toContainText("Profile validated");
  await page.getByRole("button", { name: "Continue to use profile" }).click();
  await expect(page.getByRole("heading", { name: "Choose how to use the profile" })).toBeVisible();
});

test("keeps profile metadata controls aligned at a consistent height", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();

  await expect(page.getByRole("heading", { name: "Prepare your Powercalc profile" })).toBeVisible();
  await expect(page.locator("section.profile-metadata")).toHaveCSS("border-top-width", "0px");
  await expect(page.locator(".profile-metadata > .contribution-auto")).toHaveCSS("border-top-width", "1px");
  await expect(page.getByRole("group", { name: "Product" })).toHaveCSS("border-top-width", "1px");
  const measureDevice = page.getByRole("combobox", { name: "Measurement device", exact: true });
  await measureDevice.fill("Kasa");
  await expect(page.getByRole("option", { name: "Kasa EP25", exact: true })).toBeVisible();
  await measureDevice.press("ArrowDown");
  await measureDevice.press("Enter");
  await expect(measureDevice).toHaveValue("Kasa EP25");
  const connectivity = page.getByRole("combobox", { name: "Connectivity", exact: true });
  await connectivity.click();
  await page.getByRole("option", { name: "Zigbee", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove Zigbee" })).toBeVisible();
  await page.getByRole("option", { name: "Wi-Fi", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove Wi-Fi" })).toBeVisible();
  await page.getByRole("button", { name: "Remove Wi-Fi" }).click();
  await expect(page.getByRole("button", { name: "Remove Wi-Fi" })).toBeHidden();
  await connectivity.click();
  await page.getByRole("option", { name: "Wi-Fi", exact: true }).click();
  const productControls = [
    page.getByRole("combobox", { name: "Manufacturer" }),
    page.locator('input[name="model_id"]'),
    page.locator('input[name="product_name"]'),
    page.locator('input[name="product_url"]'),
    page.locator('input[name="aliases"]'),
    page.locator('input[name="gtins"]'),
  ];
  const contributorControls = [
    page.locator('input[name="contributor"]'),
    page.locator('input[name="contributor_github"]'),
    page.locator('input[name="contributor_email"]'),
  ];
  const measurementControls = [
    page.getByRole("combobox", { name: "Measurement device", exact: true }),
    page.locator('input[name="measure_device_firmware"]'),
  ];
  const controls = [...productControls, ...contributorControls, ...measurementControls];
  const boxes = await Promise.all(controls.map((control) => control.boundingBox()));
  const heights = boxes.map((box) => box!.height);

  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
  expect(Math.min(...heights)).toBeGreaterThanOrEqual(44);
  for (const [left, right] of [[0, 1], [2, 3], [4, 5], [6, 7], [7, 8], [9, 10]] as const) {
    expect(Math.abs(boxes[left]!.y - boxes[right]!.y)).toBeLessThanOrEqual(1);
  }

  await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
  await expect(page.locator(".validation-status")).toContainText("Profile validated");
  await expect(page.getByRole("button", { name: /^Validate (profile|changes)$/ })).toBeHidden();
  const preparedPreview = page.locator(".prepared-preview");
  await expect(preparedPreview.locator("pre").first()).toBeHidden();
  await preparedPreview.locator("summary").click();
  await expect(preparedPreview.locator("pre").first()).toBeVisible();
  await page.getByRole("button", { name: "Continue to use profile" }).click();
  await expect(page.getByRole("heading", { name: "Choose how to use the profile" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /GitHub pull request/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Manual contribution/ })).toBeVisible();
});

test("shows required field errors inline with red borders and keeps edited previews stale", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const manufacturer = page.getByRole("combobox", { name: "Manufacturer", exact: true });
  const model = page.locator('input[name="model_id"]');
  const product = page.locator('input[name="product_name"]');
  const originalManufacturer = await manufacturer.inputValue();
  const originalModel = await model.inputValue();
  const originalProduct = await product.inputValue();
  await manufacturer.fill("");
  await model.fill(" ");
  await product.fill("");
  await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
  const summary = page.locator(".validation-summary");
  await expect(summary.locator("li")).toHaveCount(3);
  await expect(manufacturer).toBeFocused();
  for (const control of [manufacturer, model, product]) {
    await expect(control).toHaveAttribute("aria-invalid", "true");
    await expect(control).toHaveCSS("border-top-color", "rgb(255, 123, 114)");
  }
  await expect(page.getByText("Fields marked")).toBeVisible();
  await expect(page.locator("measure-result-view .required-marker")).toHaveCount(7);
  await summary.getByRole("button", { name: /Product name/ }).click();
  await expect(product).toBeFocused();
  await product.fill(originalProduct);
  await expect(product).toHaveAttribute("aria-invalid", "false");
  await manufacturer.fill(originalManufacturer);
  await model.fill(originalModel);
  await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
  const next = page.getByRole("button", { name: "Continue to use profile" });
  await expect(next).toBeEnabled();
  await product.fill("Changed product");
  await expect(next).toBeHidden();
  await expect(page.getByText("Your changes have not been validated yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Validate changes" })).toBeVisible();
});

test("shows schema validation failures at the affected specification", async ({ page }) => {
  await page.route("**/contribution/preview", (route) => route.fulfill({
    status: 400, contentType: "application/json",
    body: JSON.stringify({ code: "invalid_metadata", field: "device_specs.rated_power", message: "Rated power must be at least 0." }),
  }));
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
  const ratedPower = page.getByRole("spinbutton", { name: "Rated power (W)", exact: true });
  await expect(ratedPower).toHaveAttribute("aria-invalid", "true");
  await expect(ratedPower).toBeFocused();
  await expect(page.locator(".validation-summary")).toContainText("Rated power must be at least 0.");
  await expect(page.locator('[id="device_specs.rated_power-error"]')).toHaveText("Rated power must be at least 0.");
});

test("validates email and repeated manufacturer names when leaving the field", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const product = page.getByRole("textbox", { name: "Product name", exact: true });
  const email = page.getByRole("textbox", { name: "Email", exact: true });
  await page.getByRole("combobox", { name: "Manufacturer", exact: true }).fill("Anko");
  await product.fill("Anko Bladiebla");
  await email.fill("not-an-email");
  await email.press("Tab");
  await expect(product).toHaveAttribute("aria-invalid", "true");
  await expect(email).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("#product_name-error")).toContainText("Leave out the manufacturer");
  await expect(page.locator("#contributor_email-error")).toContainText("valid email address");
  await product.fill("Bladiebla");
  await email.fill("tester@example.com");
  await email.press("Tab");
  await expect(product).toHaveAttribute("aria-invalid", "false");
  await expect(email).toHaveAttribute("aria-invalid", "false");
});

test("opens settings from setup with the configured power meter", async ({ page }) => {
  await startAverageSetup(page);
  await page.getByRole("button", { name: "Change power meter" }).click();

  await expect(page.getByRole("heading", { name: "Measurement defaults" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Power measurement device" })).toHaveValue("Shelly Plug S");
  await expect(page.getByLabel("Power measurement device firmware")).toHaveValue("1.2.3");
  await expect(page.getByRole("combobox", { name: "Type", exact: true })).toHaveValue("Home Assistant sensor");
  await expect(page.getByRole("combobox", { name: "Power sensor" })).toHaveValue("Plug power · sensor.plug_power");

  const deviceName = page.getByRole("combobox", { name: "Power measurement device" });
  await deviceName.fill("plus");
  await expect(page.getByRole("listbox", { name: "Power measurement device options" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Shelly Plus Plug S" })).toBeVisible();
  await expect(page.getByRole("option", { name: "Aeotec ZWA023" })).toBeHidden();
  await deviceName.press("ArrowDown");
  await deviceName.press("Enter");
  await expect(deviceName).toHaveValue("Shelly Plus Plug S");
  await expect(page.getByRole("listbox", { name: "Power measurement device options" })).toBeHidden();

  await page.getByRole("button", { name: "Profile metadata" }).click();
  await expect(page.getByLabel("Contributor name")).toHaveValue("Powercalc Tester");
  await expect(page.getByLabel("GitHub username")).toHaveValue("powercalc-tester");
  await expect(page.getByLabel("Email (optional)")).toHaveValue("tester@example.com");
});
