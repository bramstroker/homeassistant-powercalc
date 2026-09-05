import { afterEach } from "vitest";
import type { SessionLog } from "./log";
import "./log";

describe("session log", () => {
  afterEach(() => document.body.replaceChildren());

  it("stays hidden without entries and opens as an overlay", async () => {
    const element = document.createElement("measure-session-log") as SessionLog;
    document.body.append(element);
    await element.updateComplete;
    expect(element.shadowRoot?.querySelector(".log-toggle")).toBeNull();

    element.logs = ["First log", "Second log"];
    await element.updateComplete;
    const toggle = element.shadowRoot?.querySelector(".log-toggle") as HTMLButtonElement;
    expect(toggle.textContent).toContain("2");
    toggle.click();
    await element.updateComplete;
    expect(element.shadowRoot?.querySelector(".log-overlay")?.textContent).toContain("Second log");
  });

  it("marks warnings and auto-scrolls when entries arrive", async () => {
    const warning = "Discarding measurement: 0 watt was read from the power meter";
    const element = document.createElement("measure-session-log") as SessionLog;
    element.logs = [warning];
    element.warnings = [warning];
    element.open = true;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot?.querySelector(".log p.warning")?.textContent).toContain(warning);
    const container = element.shadowRoot?.querySelector(".log") as HTMLDivElement;
    Object.defineProperty(container, "scrollHeight", { value: 240, configurable: true });
    Object.defineProperty(container, "scrollTop", { value: 0, writable: true, configurable: true });
    element.logs = [...element.logs, "Second log"];
    await element.updateComplete;
    expect(container.scrollTop).toBe(240);
  });

  it.each(["Escape", "button"])("returns focus to the toggle when closed with %s", async (method) => {
    const element = document.createElement("measure-session-log");
    element.logs = ["First log"];
    document.body.append(element);
    await element.updateComplete;
    const toggle = element.shadowRoot!.querySelector<HTMLButtonElement>(".log-toggle")!;
    toggle.click();
    await element.updateComplete;
    const close = element.shadowRoot!.querySelector<HTMLButtonElement>(".log-head button")!;
    expect(element.shadowRoot!.activeElement).toBe(close);
    expect(toggle.getAttribute("aria-controls")).toBe("session-log");
    if (method === "Escape") close.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    else close.click();
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector(".log-overlay")).toBeNull();
    expect(element.shadowRoot!.activeElement).toBe(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.hasAttribute("aria-controls")).toBe(false);
  });
});
