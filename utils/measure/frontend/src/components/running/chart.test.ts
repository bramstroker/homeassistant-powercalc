import { afterEach } from "vitest";
import type { PowerChart } from "./chart";
import "./chart";

describe("power chart", () => {
  afterEach(() => document.body.replaceChildren());

  it("draws streamed samples with the latest value and range", async () => {
    const element = document.createElement("measure-power-chart") as PowerChart;
    element.samples = [4.2, 5.1, 4.8];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot?.querySelector("svg.spark polyline.line")?.getAttribute("points")).toContain(",");
    expect(element.shadowRoot?.querySelector(".chart-head strong")?.textContent).toContain("4.8");
    expect(element.shadowRoot?.querySelector(".chart-scale")?.textContent).toContain("peak 5.1 W");
  });

  it("renders nothing until a sample arrives", async () => {
    const element = document.createElement("measure-power-chart") as PowerChart;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot?.querySelector(".chart")).toBeNull();
  });
});
