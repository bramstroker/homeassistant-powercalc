import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { contributionPreview, mockApi, startedSnapshot } from "./mock-api";
import type { SessionSnapshot, SessionSummary } from "../src/types";

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

test("preserves unfinished setup through settings and resets it for a new measurement", async ({ page }) => {
  await startAverageSetup(page);
  const duration = page.getByRole("spinbutton", { name: "Duration (seconds)", exact: true });
  const sessionName = page.locator('input[name="session_name"]');
  await duration.fill("300");
  await sessionName.fill("Living room standby");
  await page.getByRole("button", { name: "Change power meter" }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(duration).toHaveValue("300");
  await expect(sessionName).toHaveValue("Living room standby");
  await duration.fill("");
  await page.getByRole("button", { name: /Settings/ }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(duration).toHaveValue("");
  await page.getByRole("button", { name: "All sessions", exact: true }).click();
  await startAverageSetup(page);
  await expect(duration).toHaveValue("60");
  await expect(sessionName).toHaveValue("");
});

test("keeps keyboard focus in the JSON inspector and restores its trigger on Escape", async ({ page }) => {
  await page.getByRole("button", { name: "Open", exact: true }).click();
  const trigger = page.getByRole("button", { name: "View model.json", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "model.json" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  for (let index = 0; index < 4; index++) {
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Prepare profile", exact: true })).not.toBeFocused();
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("keeps profile validation visible on mobile with optional fields collapsed", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const validate = page.getByRole("button", { name: "Validate profile", exact: true });
  await expect(validate).toBeInViewport();
  await expect(page.getByRole("textbox", { name: "Notes", exact: true })).toBeHidden();
  await expect(page.getByRole("spinbutton", { name: "Rated power (W)", exact: true })).toBeHidden();
  await page.getByText("Device specifications (optional)", { exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Rated power (W)", exact: true })).toBeVisible();
  await expect(validate).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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

test("follows the system color scheme and persists an explicit theme", async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.reload();
  const app = page.locator("powercalc-measure-app");
  const theme = app.getByRole("button", { name: /Color theme:/ });
  const sessions = page.locator("measure-sessions-view");

  await app.evaluate((element) => {
    const shell = element as HTMLElement & { sessions: SessionSummary[]; requestUpdate: () => void };
    const completed = shell.sessions[0];
    if (!completed) return;
    shell.sessions = [
      completed,
      { ...completed, session_id: "session-completed-2", product_name: "Recorder", model_id: "" },
      { ...completed, session_id: "session-completed-3", product_name: "Recorder", model_id: "" },
      {
        ...completed,
        session_id: "session-cancelled",
        state: "cancelled",
        product_name: "Bedroom",
        model_id: "Room",
        can_resume: true,
        completed: 2,
        total: 4,
        percent: 50,
      },
    ];
    shell.requestUpdate();
  });
  await expect(sessions.locator("article")).toHaveCount(4);

  await expect(app).toHaveAttribute("data-theme", "system");
  await expect(theme).toHaveAttribute("aria-label", /Color theme: System/);
  await expect(app).toHaveCSS("background-color", "rgb(244, 247, 251)");
  expect(await sessions.locator(".sessions").evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(" "))).toHaveLength(3);
  expect(await sessions.locator(".primary-actions").first().evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(" "))).toHaveLength(3);
  expect(await sessions.locator(".primary-actions button").evaluateAll((buttons) => buttons.every((button) => button.scrollWidth <= button.clientWidth))).toBe(true);
  expect(await sessions.locator("article").first().evaluate((card) => getComputedStyle(card).backgroundColor))
    .not.toBe(await sessions.locator(".panel").evaluate((panel) => getComputedStyle(panel).backgroundColor));
  await page.screenshot({ path: testInfo.outputPath("sessions-light.png"), fullPage: true });

  await theme.click();
  await expect(app).toHaveAttribute("data-theme", "light");
  await expect(theme).toHaveAttribute("title", "Color theme: Light");
  await theme.click();
  await expect(app).toHaveAttribute("data-theme", "dark");
  await expect(app).toHaveCSS("background-color", "rgb(13, 17, 25)");
  expect(await sessions.locator("article").first().evaluate((card) => getComputedStyle(card).backgroundColor))
    .not.toBe(await sessions.locator(".panel").evaluate((panel) => getComputedStyle(panel).backgroundColor));
  await page.screenshot({ path: testInfo.outputPath("sessions-dark.png"), fullPage: true });

  await page.reload();
  await expect(app).toHaveAttribute("data-theme", "dark");
  await expect(theme).toHaveAttribute("aria-label", /Color theme: Dark/);
  await theme.click();
  await expect(app).toHaveAttribute("data-theme", "system");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(app).toHaveCSS("background-color", "rgb(13, 17, 25)");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#0d1119");
  await page.setViewportSize({ width: 390, height: 900 });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await expect(app).toHaveCSS("background-color", "rgb(244, 247, 251)");
  await expect(page.getByRole("button", { name: "Settings" })).toHaveCSS("background-color", "rgb(237, 242, 247)");
  await expect(page.getByRole("button", { name: "Measure again" })).toHaveCSS("background-color", "rgb(255, 255, 255)");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect(page.getByRole("button", { name: "Open", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Diagnostics" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("sessions-light-mobile.png"), fullPage: true });
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

test("loads tracked recorder entities after choosing the complex-profile flow", async ({ page }) => {
  await page.getByRole("button", { name: "New measurement" }).click();
  await page.getByRole("button", { name: /Recorder/ }).click();

  await page.getByRole("combobox", { name: "What do you want to create?" }).click();
  await page.getByRole("option", { name: "Data for a complex power profile (experimental)" }).click();

  const tracked = page.getByRole("combobox", { name: "Tracked entities" });
  await tracked.click();
  await expect(page.getByRole("option", { name: "Living room thermostat · climate.living_room" })).toBeVisible();
  await expect(page.locator('input[name="model_id"]')).toHaveCount(0);
  await expect(page.locator('input[name="product_name"]')).toHaveCount(0);
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
    await expect(setup.locator(".multiple-lights .help-content")).toBeHidden();
    await expect(setup.getByRole("group", { name: "What do you want to measure?" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: testInfo.outputPath("setup.png"), fullPage: true });

    const discoveryHelp = setup.locator('summary[aria-label="Light not found?"]');
    const initialGridBounds = await grid.boundingBox();
    await discoveryHelp.click();
    await expect(setup.locator(".discovery-help p")).toBeVisible();
    expect(await grid.boundingBox()).toEqual(initialGridBounds);
    await discoveryHelp.press("Escape");
    await expect(setup.locator(".discovery-help p")).toBeHidden();

    const toggle = setup.getByLabel("Measure multiple lights", { exact: true });
    await toggle.scrollIntoViewIfNeeded();
    const toggleBefore = await toggle.boundingBox();
    await toggle.check();
    expect(await toggle.boundingBox()).toEqual(toggleBefore);
    await expect(setup.locator(".multiple-lights .help-content")).toBeHidden();
    const multipleHelp = setup.locator('summary[aria-label="About measuring multiple lights"]');
    await multipleHelp.focus();
    await multipleHelp.press("Enter");
    await expect(setup.locator(".multiple-lights .help-content")).toBeVisible();
    await expect(setup.getByRole("link", { name: "Home Assistant light group" })).toBeVisible();
    expect(await toggle.boundingBox()).toEqual(toggleBefore);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await multipleHelp.press("Escape");
    await setup.getByRole("combobox", { name: "Lights", exact: true }).click();
    await setup.getByRole("option", { name: "Desk lamp · light.desk" }).click();
    await setup.getByRole("option", { name: "Floor lamp · light.floor" }).click();
    await setup.getByRole("combobox", { name: "Lights", exact: true }).press("Escape");
    expect(await toggle.boundingBox()).toEqual(toggleBefore);
    await expect(setup.locator('measure-combobox[name="light_entity_id"]')).toHaveCount(1);
    await expect(light.locator(".tag")).toHaveCount(2);
    await expect(setup.getByRole("button", { name: "Add another light" })).toHaveCount(0);
    await expect(setup.getByRole("spinbutton", { name: "Number of lights" })).toHaveValue("2");
    const countHelp = setup.locator('summary[aria-label="Number of lights"]');
    await countHelp.click();
    await expect(setup.getByText(/Measured power is divided by this value/)).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("multiple-lights-help.png"), fullPage: true });
    await countHelp.press("Escape");
    await page.screenshot({ path: testInfo.outputPath("multiple-lights.png"), fullPage: true });
    await light.getByRole("button", { name: "Remove Floor lamp · light.floor" }).click();
    await expect(light.locator(".tag")).toHaveCount(1);
    await expect(setup.getByRole("spinbutton", { name: "Number of lights" })).toHaveValue("1");
    await toggle.uncheck();
    await expect(setup.getByRole("combobox", { name: "Light", exact: true })).toHaveValue("Desk lamp · light.desk");
    await expect(setup.locator(".multiple-lights .help-content")).toBeHidden();
  });
}

test("submits light tags as distinct controller entities", async ({ page }) => {
  await page.getByRole("button", { name: "New measurement" }).click();
  await page.getByRole("button", { name: /Light bulb/ }).click();
  await page.getByLabel("Measure multiple lights", { exact: true }).check();
  const picker = page.getByRole("combobox", { name: "Lights", exact: true });
  await picker.click();
  await page.getByRole("option", { name: "Desk lamp · light.desk" }).click();
  await page.getByRole("option", { name: "Floor lamp · light.floor" }).click();
  await picker.press("Escape");
  const request = page.waitForRequest("**/api/preflight");
  await page.getByRole("button", { name: "Check light and setup", exact: true }).click();
  expect((await request).postDataJSON()).toMatchObject({
    controller: { type: "hass_multi", entity_ids: ["light.desk", "light.floor"] },
    multiple_light_count: 2,
  });
  await expect(page.getByRole("heading", { name: "Ready for the bench" })).toBeVisible();
});

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
  await expect(page.getByRole("button", { name: "Close log" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("complementary", { name: "Measurement log" })).toBeHidden();
  await expect(page.getByRole("button", { name: /View log/ })).toBeFocused();
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
    ...startedSnapshot,
    session_id: "session-completed", state: "completed", phase: "Measurement complete",
    progress: { completed: 1, total: 1, skipped: 0, percent: 100, estimated_remaining_seconds: 0 },
    summary: { "Average power": "4.2 W", Duration: "6.5 s" },
    request: { ...startedSnapshot.request, measure_device: "Test meter", power_meter: { type: "dummy" } },
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
    await page.getByRole("button", { name: "Continue to submit profile" }).click();
    const github = page.getByRole("radio", { name: /^GitHub pull request/ });
    const manual = page.getByRole("radio", { name: /^Manual contribution/ });
    await github.focus();
    await github.press("ArrowRight");
    await expect(manual).toBeFocused();
    await expect(manual).toBeChecked();
    await manual.press("ArrowRight");
    await expect(github).toBeFocused();
    await expect(github).toBeChecked();
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

test("preserves unfinished profile fields, list rows and tags when navigating back to Result", async ({ page }) => {
  await page.route("**/api/sessions/session-completed/contribution/preview", (route) => route.fulfill({
    json: { ...contributionPreview, product_name: "Edited lamp" },
  }));
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const product = page.locator('input[name="product_name"]');
  const aliases = page.locator('measure-string-list-input[name="aliases"]');
  const aliasInputs = aliases.locator("input");
  const meter = page.getByRole("combobox", { name: "Measurement device", exact: true });
  await product.fill("Edited lamp ");
  await aliasInputs.first().fill("Alias one ");
  await aliases.getByRole("button", { name: "Add another alias" }).click();
  await meter.fill("Custom meter");
  await page.getByText("Device specifications (optional)", { exact: true }).click();
  await page.getByRole("combobox", { name: "Connectivity", exact: true }).click();
  await page.getByRole("option", { name: "Zigbee", exact: true }).click();
  const progress = page.getByRole("navigation", { name: "Measurement progress" });
  await progress.getByRole("button", { name: "Result", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.getByRole("button", { name: "Prepare profile" }).click();

  await expect(product).toHaveValue("Edited lamp ");
  await expect(aliasInputs).toHaveCount(2);
  await expect(aliasInputs.first()).toHaveValue("Alias one ");
  await expect(aliasInputs.nth(1)).toHaveValue("");
  await expect(meter).toHaveValue("Custom meter");
  await page.getByText("Device specifications (optional)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove Zigbee" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue to submit profile" })).toBeHidden();
  await page.getByRole("button", { name: "Validate changes" }).click();
  await expect(page.locator(".validation-status")).toContainText("Profile validated");
  await page.getByRole("button", { name: "Continue to submit profile" }).click();
  await expect(page.getByRole("heading", { name: "Choose how to submit the profile" })).toBeVisible();
  const prepareStep = progress.getByRole("button", { name: "Prepare", exact: true });
  await prepareStep.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Prepare your Powercalc profile" })).toBeVisible();
  await expect(product).toHaveValue("Edited lamp");
  await expect(page.getByRole("button", { name: "Continue to submit profile" })).toBeEnabled();
  await page.getByRole("button", { name: "Continue to submit profile" }).click();
  const resultStep = progress.getByRole("button", { name: "Result", exact: true });
  await resultStep.focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("heading", { name: "Measurement complete" })).toBeVisible();
  await expect(progress.getByRole("button")).toHaveCount(0);
});

test("submits aliases and barcodes as individual metadata rows", async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/sessions/session-completed/contribution/preview", async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ json: contributionPreview });
  });
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();

  const aliases = page.locator('measure-string-list-input[name="aliases"]');
  await aliases.locator("input").first().fill("LWA017-A");
  await aliases.getByRole("button", { name: "Add another alias" }).click();
  await aliases.locator("input").nth(1).fill("LWA017-B");

  const barcodes = page.locator('measure-string-list-input[name="gtins"]');
  await expect(barcodes.locator("input").first()).toHaveAttribute("inputmode", "numeric");
  await barcodes.locator("input").first().fill("12345678");
  await barcodes.getByRole("button", { name: "Add another barcode" }).click();
  await barcodes.locator("input").nth(1).fill("1234567890123");
  await page.getByRole("button", { name: "Validate changes" }).click();

  await expect.poll(() => submitted).toMatchObject({
    aliases: ["LWA017-A", "LWA017-B"],
    gtins: ["12345678", "1234567890123"],
  });
  await expect(page.locator(".validation-status")).toContainText("Profile validated");
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
  await page.getByText("Device specifications (optional)", { exact: true }).click();
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
    page.locator('measure-string-list-input[name="aliases"] input').first(),
    page.locator('measure-string-list-input[name="gtins"] input').first(),
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
  await page.getByRole("button", { name: "Continue to submit profile" }).click();
  await expect(page.getByRole("heading", { name: "Choose how to submit the profile" })).toBeVisible();
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
    expect(await control.evaluate((element) => {
      const marker = document.createElement("span");
      marker.style.color = "var(--danger)";
      element.getRootNode().appendChild(marker);
      const matchesTheme = getComputedStyle(element).borderTopColor === getComputedStyle(marker).color;
      marker.remove();
      return matchesTheme;
    })).toBe(true);
  }
  await expect(page.getByText("Fields marked")).toBeVisible();
  await expect(page.locator("measure-profile-prepare-view .required-marker")).toHaveCount(7);
  await summary.getByRole("button", { name: /Product name/ }).click();
  await expect(product).toBeFocused();
  await product.fill(originalProduct);
  await expect(product).toHaveAttribute("aria-invalid", "false");
  await manufacturer.fill(originalManufacturer);
  await model.fill(originalModel);
  await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
  const next = page.getByRole("button", { name: "Continue to submit profile" });
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
