import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResultPlot } from "./plot";
import type { PlotSpec } from "../../types";

const plot: PlotSpec = {
  id: "brightness", title: "Brightness", kind: "scatter", source: "brightness.csv",
  x_label: "Brightness", y_label: "Power (W)", series: [],
};

describe("result plot lifecycle", () => {
  const observe = vi.fn();
  const disconnect = vi.fn();
  let resized: () => void;

  beforeEach(() => {
    observe.mockClear();
    disconnect.mockClear();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: () => void) { resized = callback; }
      observe = observe;
      disconnect = disconnect;
    });
    // Count draw attempts without requiring a canvas implementation in jsdom.
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  });

  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

  async function mount() {
    const element = new ResultPlot();
    element.plot = plot;
    document.body.append(element);
    await element.updateComplete;
    return element;
  }

  it("draws once on initial update and redraws on resize or new plot data", async () => {
    const element = await mount();
    const canvas = element.shadowRoot!.querySelector("canvas")!;
    expect(observe).toHaveBeenCalledExactlyOnceWith(canvas);
    expect(canvas.getContext).toHaveBeenCalledTimes(1);

    Object.defineProperty(canvas, "clientWidth", { value: 400, configurable: true });
    resized();
    expect(canvas.style.height).toBe("300px");
    expect(canvas.getContext).toHaveBeenCalledTimes(2);

    element.plot = { ...plot, title: "Updated brightness" };
    await element.updateComplete;
    expect(canvas.getContext).toHaveBeenCalledTimes(3);
    expect(canvas.getAttribute("aria-label")).toBe("Updated brightness: Power (W) by Brightness");
  });

  it("disconnects the observer and resumes drawing after reattachment", async () => {
    const element = await mount();
    const canvas = element.shadowRoot!.querySelector("canvas")!;
    element.remove();
    expect(disconnect).toHaveBeenCalledTimes(1);
    resized();
    element.partial = true;
    await element.updateComplete;
    expect(canvas.getContext).toHaveBeenCalledTimes(1);

    document.body.append(element);
    expect(observe).toHaveBeenCalledTimes(2);
    expect(canvas.getContext).toHaveBeenCalledTimes(2);
    resized();
    expect(canvas.getContext).toHaveBeenCalledTimes(3);
  });

  it("does not start observing if removed before the first update", async () => {
    const element = new ResultPlot();
    element.plot = plot;
    document.body.append(element);
    element.remove();
    await element.updateComplete;
    expect(observe).not.toHaveBeenCalled();
    expect(HTMLCanvasElement.prototype.getContext).not.toHaveBeenCalled();

    document.body.append(element);
    expect(observe).toHaveBeenCalledTimes(1);
    expect(HTMLCanvasElement.prototype.getContext).toHaveBeenCalledTimes(1);
  });

  it("still draws without ResizeObserver support", async () => {
    vi.stubGlobal("ResizeObserver", undefined);
    const element = await mount();
    expect(observe).not.toHaveBeenCalled();
    expect(element.shadowRoot!.querySelector("canvas")!.getContext).toHaveBeenCalledTimes(1);
  });
});
