import { LitElement, css, html, svg } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("measure-power-chart")
export class PowerChart extends LitElement {
  @property({ attribute: false })
  samples: number[] = [];

  static readonly styles = css`
    :host { display: block; }
    .chart { position: relative; margin-top: 1.4rem; }
    .chart-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
    .chart-head span { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .chart-head strong { font: 700 clamp(1.4rem, 5vw, 2rem)/1 "DIN Alternate", sans-serif; color: var(--signal-strong); letter-spacing: -0.02em; }
    .chart-head strong small { margin-left: 0.15em; color: var(--muted); font-size: 0.5em; letter-spacing: 0.06em; }
    .spark { display: block; width: 100%; height: 110px; margin-top: 0.6rem; }
    .spark .area { fill: color-mix(in srgb, var(--signal) 14%, transparent); stroke: none; }
    .spark .line { fill: none; stroke: var(--signal); stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
    .chart-scale { display: flex; justify-content: space-between; margin-top: 0.3rem; color: var(--muted); font: 0.68rem/1 ui-monospace, monospace; }
  `;

  render() {
    if (!this.samples.length) return undefined;
    const latest = this.samples.at(-1) ?? 0;
    const max = Math.max(...this.samples);
    const min = Math.min(...this.samples);
    const range = max - min || 1;
    const count = this.samples.length;
    const point = (watt: number, index: number): [number, number] => {
      const x = count === 1 ? 100 : index / (count - 1) * 100;
      const y = 30 - (watt - min) / range * 28;
      return [x, y];
    };
    const line = this.samples.map((watt, index) => point(watt, index).map((value) => value.toFixed(2)).join(",")).join(" ");
    const area = `0,32 ${line} 100,32`;
    return html`
      <div class="chart">
        <div class="chart-head">
          <span>Live power</span>
          <strong>${latest.toFixed(1)}<small>W</small></strong>
        </div>
        <svg class="spark" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label="Live power readings, currently ${latest.toFixed(1)} watt">
          ${svg`<polygon class="area" points=${area} />`}
          ${svg`<polyline class="line" points=${line} />`}
        </svg>
        <div class="chart-scale"><span>${min.toFixed(1)} W</span><span>peak ${max.toFixed(1)} W</span></div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "measure-power-chart": PowerChart;
  }
}
