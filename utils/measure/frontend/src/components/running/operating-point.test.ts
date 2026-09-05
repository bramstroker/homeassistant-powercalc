import { afterEach } from "vitest";
import type { OperatingPoint } from "../../types";
import type { OperatingPointView } from "./operating-point";
import "./operating-point";

describe("operating point", () => {
  afterEach(() => document.body.replaceChildren());

  it.each([
    [
      { type: "light", on: true, brightness: 128, color_temp_mired: 370, hue: 32_768, saturation: 128 } as OperatingPoint,
      ["Brightness 50%", "Color temp 2703 K", "Hue 180°", "Saturation 50%"],
    ],
    [{ type: "light", on: false } as OperatingPoint, ["Off"]],
    [{ type: "speaker", volume: 40, muted: false } as OperatingPoint, ["Volume 40%"]],
    [{ type: "speaker", volume: 0, muted: true } as OperatingPoint, ["Muted"]],
    [{ type: "fan", percentage: 65, on: true } as OperatingPoint, ["Fan speed 65%"]],
    [{ type: "charging", battery_level: 72, charging: true } as OperatingPoint, ["Battery 72%", "Charging"]],
  ])("renders compact state for %#", async (point, expected) => {
    const element = document.createElement("measure-operating-point") as OperatingPointView;
    element.point = point;
    document.body.append(element);
    await element.updateComplete;

    const state = element.shadowRoot?.querySelector(".operating-point");
    expect(state?.getAttribute("aria-live")).toBe("polite");
    expect(state?.textContent).toContain("Current measurement point");
    for (const value of expected) expect(state?.textContent).toContain(value);
  });

  it.each([
    [
      { type: "light", on: true, brightness: 128, color_temp_mired: 370, hue: 32_768, saturation: 128, effect: "candle" } as OperatingPoint,
      ["brightness", "color-temp", "hue", "saturation", "effect"],
    ],
    [{ type: "light", on: false } as OperatingPoint, ["off"]],
    [{ type: "speaker", volume: 40, muted: false } as OperatingPoint, ["volume"]],
    [{ type: "speaker", volume: 0, muted: true } as OperatingPoint, ["muted"]],
    [{ type: "fan", percentage: 65, on: true } as OperatingPoint, ["fan-speed"]],
    [{ type: "fan", percentage: 0, on: false } as OperatingPoint, ["off"]],
    [{ type: "charging", battery_level: 72, charging: true } as OperatingPoint, ["battery", "charging"]],
    [{ type: "charging", battery_level: 25, charging: false } as OperatingPoint, ["battery", "not-charging"]],
  ])("adds an icon to every chip for %#", async (point, icons) => {
    const element = document.createElement("measure-operating-point") as OperatingPointView;
    element.point = point;
    document.body.append(element);
    await element.updateComplete;

    const chips = [...element.shadowRoot?.querySelectorAll(".state-chip") ?? []];
    const renderedIcons = [...element.shadowRoot?.querySelectorAll("[data-state-icon]") ?? []];
    expect(renderedIcons.map((icon) => icon.getAttribute("data-state-icon"))).toEqual(icons);
    expect(renderedIcons).toHaveLength(chips.length);
    for (const icon of renderedIcons) expect(icon.getAttribute("aria-hidden")).toBe("true");
  });
});
