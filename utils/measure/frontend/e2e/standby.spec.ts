import { expect, test } from "@playwright/test";
import { completedSnapshot, contributionPreview, mockApi } from "./mock-api";

test("uses detected connectivity for the first standby suggestion and preserves clearing", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/sessions/session-completed/contribution", route => route.fulfill({
    json: { ...contributionPreview, job_id: null, device_specs: { connectivity: ["zigbee"] } },
  }));
  const estimates: string[][] = [];
  await page.route("**/api/library/standby-estimate?*", route => {
    estimates.push(new URL(route.request().url()).searchParams.getAll("connectivity"));
    return route.fulfill({ json: { power_w: 0.25, basis: "connectivity", profile_count: 8 } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  await expect(page.getByRole("button", { name: "Use estimated standby: 0.25 W" })).toBeVisible();
  expect(estimates).toEqual([["zigbee"]]);
  await page.getByText("Device specifications (optional)", { exact: true }).click();
  await page.getByRole("button", { name: "Remove Zigbee", exact: true }).click();
  await expect(page.getByRole("button", { name: "Use estimated standby: 0.4 W" })).toBeVisible();
  await page.getByRole("button", { name: "Back to result", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  await page.getByText("Device specifications (optional)", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove Zigbee", exact: true })).toHaveCount(0);
  expect(estimates).toEqual([["zigbee"]]);
});

for (const kind of ["light", "fan", "recorder"] as const) {
  test(`confirms standby retry for a simulated ${kind} session`, async ({ page }) => {
    await mockApi(page);
    await page.route("**/api/sessions/session-completed", async route => {
      const snapshot = { ...completedSnapshot, request: { ...completedSnapshot.request, measure_type: kind, power_meter: { type: "dummy" },
        controller: kind === "recorder" ? null : { type: "dummy" },
        ...(kind === "recorder" ? { recorder_purpose: "complex_profile", profile_recipe: "generic" } : {}),
      } };
      await route.fulfill({ json: snapshot });
    });
    if (kind !== "light") {
      await page.route("**/api/sessions/session-completed/contribution", route => route.fulfill({
        json: { ...contributionPreview, device_type: kind === "fan" ? "fan" : "generic", standby_power: 0.4 },
      }));
    }
    let attempts = 0;
    await page.route("**/api/sessions/session-completed/standby", async route => {
      expect(route.request().postDataJSON()).toMatchObject({ confirmed: true });
      attempts++;
      await route.fulfill({ json: { status: attempts === 1 ? "measured" : "unavailable", power_w: attempts === 1 ? 0.65 : null } });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Open", exact: true }).click();
    await page.getByRole("button", { name: "Prepare profile" }).click();
    const retry = page.getByRole("button", { name: "Measure standby", exact: true });
    await expect(retry).toBeEnabled();
    await retry.click();
    await expect(page.getByText(/Results are simulated for testing/)).toBeVisible();
    if (kind === "recorder") await expect(page.getByText(/Put the device into its intended standby state first/)).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(attempts).toBe(0);
    await page.getByRole("checkbox", { name: "Estimated", exact: true }).check();
    await retry.click();
    await page.getByRole("button", { name: "Confirm and measure standby" }).click();
    await expect(page.getByRole("spinbutton", { name: /Standby power/ })).toHaveValue("0.65");
    await expect(page.getByRole("checkbox", { name: "Estimated", exact: true })).not.toBeChecked();
    if (kind === "light") {
      await expect(page.getByRole("dialog").getByText(/Measured 0.65 W per light/)).toBeVisible();
      await page.getByRole("button", { name: "Done", exact: true }).click();
    }
    await retry.click();
    await page.getByRole("button", { name: "Confirm and measure standby" }).click();
    await expect(page.getByText(/Your entered value is unchanged/)).toBeVisible();
    await expect(page.getByRole("spinbutton", { name: /Standby power/ })).toHaveValue("0.65");
  });
}

test("opens profile settings from contributor guidance and preserves standby edits", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const standby = page.getByRole("spinbutton", { name: /Standby power/ });
  await standby.fill("0.25");
  await page.getByRole("checkbox", { name: "Estimated", exact: true }).check();
  await page.getByRole("button", { name: "profile settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Profile metadata", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Contributor name", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(standby).toHaveValue("0.25");
  await expect(page.getByRole("checkbox", { name: "Estimated", exact: true })).toBeChecked();
});

for (const width of [1280, 390]) {
  test(`keeps standby controls compact at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Open", exact: true }).click();
    await page.getByRole("button", { name: "Prepare profile" }).click();
    const standby = page.getByRole("spinbutton", { name: /Standby power/ });
    const estimate = page.getByRole("button", { name: "Use estimated standby: 0.4 W" });
    await expect(estimate).toBeVisible();
    await standby.scrollIntoViewIfNeeded();
    const inputBox = await standby.boundingBox();
    const checkboxBox = await page.locator(".standby-checkbox").boundingBox();
    const buttonBox = await estimate.boundingBox();
    if (!inputBox || !checkboxBox || !buttonBox) throw new Error("Standby controls must be visible");
    expect(inputBox.width).toBeLessThan(180);
    if (width === 1280) {
      const inputCenter = inputBox.y + inputBox.height / 2;
      expect(Math.abs(checkboxBox.y + checkboxBox.height / 2 - inputCenter)).toBeLessThan(2);
      expect(Math.abs(buttonBox.y + buttonBox.height / 2 - inputCenter)).toBeLessThan(2);
    } else {
      expect(buttonBox.y).toBeGreaterThanOrEqual(inputBox.y + inputBox.height);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.locator(".standby-field").screenshot({ path: testInfo.outputPath("standby-inline.png") });
  });
}

test("recovers a completed session with zero standby without starting another measurement", async ({ page }, testInfo) => {
  await mockApi(page);
  const corrected = {
    ...contributionPreview, standby_power: 0.4, standby_power_estimated: true,
    model_json: { name: "Hue White Ambiance A60", device_type: "light", standby_power: 0.4, standby_power_estimated: true },
    pr_body: "Standby power is estimated: 0.4 W.",
  };
  let submitted = false;
  await page.route("**/api/contribution/auth", route => route.fulfill({ json: { connected: true, identity: { login: "tester" } } }));
  await page.route("**/api/sessions/session-completed/contribution", async route => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: { ...contributionPreview, job_id: null, standby_power: 0, standby_power_estimated: false } });
    }
    expect(route.request().postDataJSON()).toMatchObject({ standby_power: 0.4, standby_power_estimated: true, confirmed: true });
    submitted = true;
    return route.fulfill({ json: { status: "submitted", pull_request_url: "https://github.test/pr/1" } });
  });
  await page.route("**/api/sessions/session-completed/contribution/preview", async route => {
    expect(route.request().postDataJSON()).toMatchObject({ standby_power: 0.4, standby_power_estimated: true });
    return route.fulfill({ json: corrected });
  });
  await page.route("**/api/sessions", route => {
    expect(route.request().method()).toBe("GET");
    return route.fallback();
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  const standby = page.getByRole("spinbutton", { name: /Standby power/ });
  await expect(standby).toHaveValue("0");
  await page.getByRole("button", { name: /^Validate profile$/ }).click();
  await expect(standby).toHaveAttribute("aria-invalid", "true");
  await expect(standby).toBeFocused();
  await page.getByRole("button", { name: "Use estimated standby: 0.4 W" }).click();
  await expect(standby).toHaveValue("0.4");
  await expect(page.getByRole("checkbox", { name: "Estimated", exact: true })).toBeChecked();
  await page.screenshot({ path: testInfo.outputPath("standby-correction.png"), fullPage: true });
  await page.getByRole("button", { name: /^Validate (profile|changes)$/ }).click();
  await expect(page.getByText("0.4 W per light (estimated)", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Continue to submit profile" }).click();
  await page.locator('input[name="confirm_contribution"]').check();
  await page.getByRole("button", { name: "Confirm and open PR" }).click();
  await expect.poll(() => submitted).toBe(true);
});

test("changes standby setup and calibrates a dummy load before reconnecting the bulbs", async ({ page }) => {
  await mockApi(page);
  let calibrated = false;
  let measured = false;
  const calibration = { description: "Resistive bulb", resistance: 2400, calibrated_at: "2026-09-20T12:00:00Z", power_meter_fingerprint: "meter" };
  await page.route("**/api/dummy-load/calibration/match", route => route.fulfill({ json: calibrated ? calibration : null }));
  await page.route("**/api/sessions/session-completed/standby/calibrate", async route => {
    if (route.request().method() === "GET" && !calibrated) return route.fulfill({ json: null });
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON();
      expect(payload.setup).toMatchObject({ multiple_light_count: 1, dummy_load: { mode: "calibrate", description: "Resistive bulb" } });
      calibrated = true;
    }
    await route.fulfill({ json: { id: "job", session_id: "session-completed", status: "completed", started_at: "2026-09-20T12:00:00Z", calibration, error: null } });
  });
  await page.route("**/api/sessions/session-completed/standby", async route => {
    expect(calibrated).toBe(true);
    expect(route.request().postDataJSON().setup).toMatchObject({
      multiple_light_count: 1, parameters: { sleep_standby: 25, sample_count: 3 },
      dummy_load: { mode: "reuse", description: "Resistive bulb", resistance: 2400 },
    });
    measured = true;
    await route.fulfill({ json: { status: "measured", power_w: 0.32 } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  await page.getByRole("button", { name: "Measure standby", exact: true }).click();
  const setup = page.getByRole("dialog", { name: "Standby measurement setup" });
  await setup.getByRole("spinbutton", { name: "Number of bulbs" }).fill("1");
  await setup.getByRole("spinbutton", { name: "Standby settling time (seconds)" }).fill("25");
  await setup.getByRole("spinbutton", { name: "Samples", exact: true }).fill("3");
  await setup.getByRole("combobox", { name: "Resistive dummy load" }).selectOption("calibrate");
  await setup.getByRole("textbox", { name: "Dummy-load description" }).fill("Resistive bulb");
  await setup.getByRole("button", { name: "Calibrate dummy load" }).click();
  await expect(setup.getByText(/Calibration complete/)).toBeVisible();
  expect(measured).toBe(false);
  await setup.getByRole("button", { name: "Confirm and measure standby" }).click();
  await expect(page.getByRole("spinbutton", { name: /Standby power/ })).toHaveValue("0.32");
});

for (const width of [1280, 390]) {
  test(`shows standby setup as a modal at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Open", exact: true }).click();
    await page.getByRole("button", { name: "Prepare profile" }).click();
    const trigger = page.getByRole("button", { name: "Measure standby", exact: true });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Standby measurement setup" });
    await expect(dialog).toBeVisible();
    expect(await dialog.evaluate(element => element.matches(":modal"))).toBe(true);
    await dialog.getByRole("combobox", { name: "Resistive dummy load" }).selectOption("calibrate");
    const confirm = dialog.getByRole("button", { name: "Confirm and measure standby" });
    await expect(confirm).toBeInViewport();
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("standby-dialog.png") });
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });
}

test("keeps standby progress and the result visible in the dialog", async ({ page }) => {
  await mockApi(page);
  let finish!: () => void;
  const reading = new Promise<void>(resolve => { finish = resolve; });
  await page.route("**/api/sessions/session-completed/standby", async route => {
    await reading;
    await route.fulfill({ json: { status: "measured", power_w: 0.28 } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  await page.getByRole("button", { name: "Measure standby", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Standby measurement setup" });
  await dialog.getByRole("button", { name: "Confirm and measure standby" }).click();
  await expect(dialog.getByRole("progressbar")).toBeVisible();
  await expect(dialog.getByText(/Allow about 20s/)).toBeVisible();
  await expect(dialog.getByText("Elapsed: 1s", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Measuring standby…" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  finish();
  await expect(dialog.getByRole("progressbar")).toHaveCount(0);
  await expect(dialog.getByText(/Measured 0.28 W per light/)).toBeVisible();
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("spinbutton", { name: /Standby power/ })).toHaveValue("0.28");
});


test("reopens the dialog after a native close during standby measurement", async ({ page }) => {
  await mockApi(page);
  let finish!: () => void;
  await page.route("**/api/sessions/session-completed/standby", async route => {
    await new Promise<void>(resolve => { finish = resolve; });
    await route.fulfill({ json: { status: "measured", power_w: 0.32 } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await page.getByRole("button", { name: "Prepare profile" }).click();
  await page.getByRole("button", { name: "Measure standby", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Standby measurement setup" });
  await dialog.getByRole("button", { name: "Confirm and measure standby" }).click();
  await expect(dialog.getByRole("progressbar")).toBeVisible();
  await dialog.evaluate(element => (element as HTMLDialogElement).close());
  await expect(dialog).toHaveCount(0);
  finish();
  await expect(page.getByRole("spinbutton", { name: /Standby power/ })).toHaveValue("0.32");
  await page.getByRole("button", { name: "Measure standby", exact: true }).click();
  await expect(dialog).toBeVisible();
});

test("recovers calibration after a reload and cancels it through a short request", async ({ page }) => {
  await mockApi(page);
  let status = "running";
  const job = () => ({ id: "job", session_id: "session-completed", started_at: new Date().toISOString(), status, calibration: null, error: null });
  await page.route("**/api/sessions/session-completed/standby/calibrate", route => route.fulfill({ json: job() }));
  await page.route("**/api/sessions/session-completed/standby/calibrate/job/cancel", route => {
    status = "cancelled";
    return route.fulfill({ json: job() });
  });
  const open = async () => {
    await page.getByRole("button", { name: "Open", exact: true }).click();
    await page.getByRole("button", { name: "Prepare profile" }).click();
    await page.getByRole("button", { name: "Measure standby", exact: true }).click();
  };
  await page.goto("/");
  await open();
  await expect(page.getByRole("button", { name: "Cancel calibration" })).toBeVisible();
  await page.reload();
  await open();
  await page.getByRole("button", { name: "Cancel calibration" }).click();
  await expect(page.getByText("Calibration cancelled.", { exact: true })).toBeVisible();
});
