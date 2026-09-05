import { afterEach, describe, expect, it } from "vitest";
import { ProfileUseView } from "./use-view";

describe("profile delivery method keyboard navigation", () => {
  afterEach(() => document.body.replaceChildren());

  it.each(["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"])("selects and focuses available methods with %s", async (key) => {
    const element = new ProfileUseView();
    element.snapshot = { state: "completed" };
    element.contributionDraft = {
      eligible: true, repository: "bramstroker/homeassistant-powercalc", base_branch: "master",
      manufacturer_name: "Signify", manufacturer_directory: "signify", model_id: "LCT010",
      product_name: "Hue lamp", contributor: "Tester", device_info: {}, home_assistant: {},
      notes: "", files: [], warnings: [], commit_message: "Add profile", pr_title: "Add profile",
      pr_body: "Measured profile", branch_name: "measure/test",
    };
    document.body.append(element);
    await element.updateComplete;
    const [github, manual, local] = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    expect(github!.tabIndex).toBe(0);
    expect(manual!.tabIndex).toBe(-1);
    expect(local!.disabled).toBe(true);
    github!.focus();
    github!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    await element.updateComplete;
    expect(element.shadowRoot!.activeElement).toBe(manual);
    expect(manual!.getAttribute("aria-checked")).toBe("true");
    expect(manual!.tabIndex).toBe(0);
    expect(github!.tabIndex).toBe(-1);

    manual!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    await element.updateComplete;
    expect(element.shadowRoot!.activeElement).toBe(github);
    expect(github!.getAttribute("aria-checked")).toBe("true");
  });

  it("keeps the only available method selected and leaves Tab navigation to the browser", async () => {
    const element = new ProfileUseView();
    element.snapshot = { state: "completed" };
    document.body.append(element);
    await element.updateComplete;
    const manual = element.shadowRoot!.querySelector<HTMLButtonElement>('[role="radio"][aria-checked="true"]')!;
    manual.focus();
    manual.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    await element.updateComplete;
    expect(element.shadowRoot!.activeElement).toBe(manual);
    const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    manual.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(false);
  });
});
