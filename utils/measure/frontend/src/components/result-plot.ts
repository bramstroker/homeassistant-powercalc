import { LitElement, css, html } from "lit";
import type { PlotSpec } from "../types";
import { sharedStyles } from "../styles";

interface PlotPalette {
  background: string;
  foreground: string;
  muted: string;
  grid: string;
  signal: string;
}

export class ResultPlot extends LitElement {
  static readonly properties = {
    plot: { attribute: false },
    partial: { type: Boolean },
  };

  plot!: PlotSpec;
  partial = false;
  private resizeObserver?: ResizeObserver;

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-width: 0; }
    .plot-card { height: 100%; padding: 1rem; border: 1px solid var(--line); border-radius: 12px; background: var(--field); }
    .plot-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.75rem; }
    h4 { margin: 0; font-size: 1rem; }
    .source { display: block; margin-top: 0.2rem; color: var(--muted); font: 0.68rem/1.3 ui-monospace, monospace; overflow-wrap: anywhere; }
    .partial { display: inline-flex; padding: 0.28rem 0.5rem; border: 1px solid color-mix(in srgb, var(--signal) 65%, var(--line)); border-radius: 999px; color: var(--signal-strong); font-size: 0.68rem; white-space: nowrap; }
    canvas { display: block; width: 100%; min-height: 280px; border-radius: 8px; background: var(--well); }
    .plot-actions { display: flex; justify-content: flex-end; margin-top: 0.75rem; }
    .plot-download { min-height: 36px; padding: 0.45rem 0.75rem; font-size: 0.72rem; }
  `];

  protected firstUpdated(): void {
    const canvas = this.renderRoot.querySelector("canvas");
    if (canvas && typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => this.draw());
      this.resizeObserver.observe(canvas);
    }
    this.draw();
  }

  protected updated(): void {
    this.draw();
  }

  disconnectedCallback(): void {
    this.resizeObserver?.disconnect();
    super.disconnectedCallback();
  }

  render() {
    return html`
      <article class="plot-card">
        <div class="plot-head">
          <div><h4>${this.plot.title}</h4><span class="source">${this.plot.source}</span></div>
          ${this.partial ? html`<span class="partial">Partial result</span>` : ""}
        </div>
        <canvas role="img" aria-label="${this.plot.title}: ${this.plot.y_label} by ${this.plot.x_label}"></canvas>
        <div class="plot-actions">
          <button class="plot-download" type="button" @click=${this.download}>Download PNG</button>
        </div>
      </article>
    `;
  }

  private draw(): void {
    const canvas = this.renderRoot.querySelector("canvas");
    if (!canvas || !this.plot) return;
    const width = Math.max(320, Math.round(canvas.clientWidth || 800));
    const height = width < 520 ? 300 : 360;
    const scale = Math.min(2, globalThis.devicePixelRatio || 1);
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    canvas.style.height = `${height}px`;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(scale, 0, 0, scale, 0, 0);
    drawPlot(context, this.plot, width, height, this.palette());
  }

  private readonly download = (): void => {
    const canvas = document.createElement("canvas");
    canvas.width = 1200;
    canvas.height = 720;
    const context = canvas.getContext("2d");
    if (!context) return;
    drawPlot(context, this.plot, canvas.width, canvas.height, this.palette());
    const anchor = document.createElement("a");
    anchor.href = canvas.toDataURL("image/png");
    anchor.download = `${this.plot.id}.png`;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  };

  private palette(): PlotPalette {
    const style = getComputedStyle(this);
    const value = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
    return {
      background: value("--well", "#0a0e15"),
      foreground: value("--ink", "#eef2f7"),
      muted: value("--muted", "#93a1b5"),
      grid: value("--grid", "#55647a"),
      signal: value("--signal", "#5488e8"),
    };
  }
}

export function drawPlot(
  context: CanvasRenderingContext2D,
  plot: PlotSpec,
  width: number,
  height: number,
  palette: PlotPalette,
): void {
  const points = plot.series.flatMap((series) => series.points);
  if (!points.length) return;
  const left = 68;
  const right = 24;
  const top = plot.series.some((series) => series.label) ? 42 : 22;
  const bottom = 58;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);
  const [minX, maxX] = extent(points.map((point) => point.x));
  const [minY, maxY] = extent(points.map((point) => point.y));
  const x = (value: number) => left + (value - minX) / (maxX - minX) * plotWidth;
  const y = (value: number) => top + plotHeight - (value - minY) / (maxY - minY) * plotHeight;

  context.clearRect(0, 0, width, height);
  context.fillStyle = palette.background;
  context.fillRect(0, 0, width, height);
  context.font = '12px ui-monospace, "SFMono-Regular", monospace';
  context.lineWidth = 1;
  context.textBaseline = "middle";

  for (let index = 0; index <= 4; index += 1) {
    const ratio = index / 4;
    const gridY = top + ratio * plotHeight;
    context.strokeStyle = palette.grid;
    context.globalAlpha = 0.35;
    context.beginPath();
    context.moveTo(left, gridY);
    context.lineTo(left + plotWidth, gridY);
    context.stroke();
    context.globalAlpha = 1;
    context.fillStyle = palette.muted;
    context.textAlign = "right";
    context.fillText(format(maxY - ratio * (maxY - minY)), left - 9, gridY);
  }

  context.fillStyle = palette.muted;
  context.textAlign = "center";
  context.fillText(format(minX), left, top + plotHeight + 20);
  context.fillText(format(maxX), left + plotWidth, top + plotHeight + 20);
  context.fillStyle = palette.foreground;
  context.fillText(plot.x_label, left + plotWidth / 2, height - 14);
  context.save();
  context.translate(16, top + plotHeight / 2);
  context.rotate(-Math.PI / 2);
  context.fillText(plot.y_label, 0, 0);
  context.restore();

  for (const series of plot.series) {
    const color = series.color || palette.signal;
    if (plot.kind === "line") {
      context.strokeStyle = color;
      context.lineWidth = 2;
      context.beginPath();
      series.points.forEach((point, index) => {
        if (index === 0) context.moveTo(x(point.x), y(point.y));
        else context.lineTo(x(point.x), y(point.y));
      });
      context.stroke();
    }
    const radius = plot.kind === "line" && series.points.length > 120 ? 0 : plot.kind === "line" ? 3 : 2;
    if (radius > 0) {
      for (const point of series.points) {
        context.fillStyle = point.color || color;
        context.beginPath();
        context.arc(x(point.x), y(point.y), radius, 0, Math.PI * 2);
        context.fill();
      }
    }
  }

  const labelled = plot.series.filter((series) => series.label);
  if (labelled.length) {
    let legendX = left;
    for (const series of labelled) {
      context.fillStyle = series.color || palette.signal;
      context.fillRect(legendX, 15, 10, 10);
      context.fillStyle = palette.foreground;
      context.textAlign = "left";
      context.fillText(series.label ?? "", legendX + 15, 20);
      legendX += 28 + context.measureText(series.label ?? "").width;
      if (legendX > width - 140) break;
    }
  }
}

function extent(values: number[]): [number, number] {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    minimum = Math.min(minimum, value);
    maximum = Math.max(maximum, value);
  }
  if (minimum !== maximum) return [minimum, maximum];
  const padding = Math.max(1, Math.abs(minimum) * 0.1);
  return [minimum - padding, maximum + padding];
}

function format(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

customElements.define("measure-result-plot", ResultPlot);
