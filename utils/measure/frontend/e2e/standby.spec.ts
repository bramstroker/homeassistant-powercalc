import { expect, test } from "@playwright/test";
import { contributionPreview, mockApi } from "./mock-api";

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
