import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";
import type { Combobox } from "../src/components/shared/combobox";

test("submits a required multi-select through ElementInternals and updates native validity", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("heading", { name: "Your measurements" }).waitFor();
  await page.evaluate(async () => {
    const form = document.createElement("form");
    form.id = "combobox-test";
    const picker = document.createElement("measure-combobox");
    picker.name = "devices";
    picker.label = "Devices";
    picker.required = true;
    picker.multiple = true;
    picker.options = [{ value: "office", label: "Office" }, { value: "kitchen", label: "Kitchen" }];
    form.append(picker);
    document.body.append(form);
    await picker.updateComplete;
  });
  const form = page.locator("#combobox-test");
  const picker = form.getByRole("combobox", { name: "Devices" });
  const validity = () => form.evaluate((element: HTMLFormElement) => element.checkValidity());
  const values = () => form.evaluate((element: HTMLFormElement) => new FormData(element).getAll("devices"));
  expect(await validity()).toBe(false);
  await picker.click();
  await form.getByRole("option", { name: "Office" }).click();
  expect(await validity()).toBe(true);
  expect(await values()).toEqual(["office"]);
  await expect(picker).toHaveValue("");
  await expect(picker).toHaveAttribute("aria-required", "true");
  await form.getByRole("option", { name: "Kitchen" }).click();
  expect(await values()).toEqual(["office", "kitchen"]);
  await form.getByRole("button", { name: "Remove Office" }).click();
  expect(await values()).toEqual(["kitchen"]);
  await expect(picker).toBeFocused();
  await form.getByRole("button", { name: "Remove Kitchen" }).click();
  expect(await values()).toEqual([]);
  expect(await validity()).toBe(false);
  await expect(picker).toBeFocused();

  await form.locator("measure-combobox").evaluate(async (element: Combobox) => {
    element.setAttribute("disabled", "");
    await element.updateComplete;
  });
  expect(await validity()).toBe(true);
  await expect(picker).toBeDisabled();
});
