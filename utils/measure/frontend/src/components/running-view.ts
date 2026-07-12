import { LitElement, css, html, nothing, svg, type PropertyValues } from "lit";
import { createRef, ref } from "lit/directives/ref.js";
import type { SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";

export class RunningView extends LitElement {
  static readonly properties = {
    snapshot: { attribute: false },
    connected: { type: Boolean },
    logs: { attribute: false },
    samples: { attribute: false },
    busy: { type: Boolean },
  };

  snapshot!: SessionSnapshot;
  connected = false;
  logs: string[] = [];
  samples: number[] = [];
  busy = false;
  private readonly logContainer = createRef<HTMLDivElement>();

  static readonly styles = [sharedStyles, css`
    .instrument { position: relative; overflow: hidden; background: var(--well); border: 1px solid var(--line); border-radius: 16px; padding: clamp(1.2rem, 4vw, 2rem); }
    .instrument::before { content: ""; position: absolute; inset: 0; opacity: 0.24; pointer-events: none; background: repeating-linear-gradient(90deg, transparent 0, transparent calc(10% - 1px), var(--grid) 10%); }
    .topline { position: relative; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
    .connection { display: inline-flex; align-items: center; gap: 0.45rem; color: var(--muted); font-size: 0.82rem; }
    .connection::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); }
    .connection.connected::before { background: var(--good); box-shadow: 0 0 0 4px color-mix(in srgb, var(--good) 16%, transparent); }
    .value { position: relative; margin: 2rem 0 1.2rem; font: 700 clamp(3rem, 12vw, 7rem)/0.85 "DIN Alternate", sans-serif; letter-spacing: -0.06em; color: var(--signal-strong); }
    .value small { font-size: 0.18em; letter-spacing: 0.08em; color: var(--muted); }
    progress { position: relative; display: block; width: 100%; height: 8px; border: 0; border-radius: 99px; overflow: hidden; appearance: none; }
    progress::-webkit-progress-bar { background: var(--track); } progress::-webkit-progress-value { background: var(--signal); } progress::-moz-progress-bar { background: var(--signal); }
    .metrics { position: relative; display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1.2rem; }
    .metric span { display: block; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric strong { display: block; margin-top: 0.25rem; font: 600 1rem/1.3 ui-monospace, monospace; }
    .log { max-height: 9rem; overflow: auto; margin-top: 1rem; padding: 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); font: 0.8rem/1.6 ui-monospace, monospace; color: var(--muted); }
    .log p { margin: 0; }
    .chart { position: relative; margin-top: 1.4rem; }
    .chart-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
    .chart-head span { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .chart-head strong { font: 700 clamp(1.4rem, 5vw, 2rem)/1 "DIN Alternate", sans-serif; color: var(--signal-strong); letter-spacing: -0.02em; }
    .chart-head strong small { font-size: 0.5em; color: var(--muted); letter-spacing: 0.06em; margin-left: 0.15em; }
    .spark { display: block; width: 100%; height: 110px; margin-top: 0.6rem; }
    .spark .area { fill: color-mix(in srgb, var(--signal) 14%, transparent); stroke: none; }
    .spark .line { fill: none; stroke: var(--signal); stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
    .chart-scale { display: flex; justify-content: space-between; margin-top: 0.3rem; color: var(--muted); font: 0.68rem/1 ui-monospace, monospace; }
    @media (max-width: 640px) { .metrics { grid-template-columns: 1fr 1fr; } .topline { align-items: flex-start; flex-direction: column; } }
  `];

  protected updated(changedProperties: PropertyValues<this>): void {
    if (changedProperties.has("logs") && this.logs.length) {
      const container = this.logContainer.value;
      if (container) container.scrollTop = container.scrollHeight;
    }
  }

  render() {
    const progress = this.snapshot.progress ?? { completed: 0, total: 0 };
    const percent = progress.percent ?? (progress.total ? progress.completed / progress.total * 100 : 0);
    return html`
      <section class="panel" aria-labelledby="running-title">
        <p class="eyebrow">03 / Measurement</p>
        <h2 id="running-title">${this.runningTitle()}</h2>
        <div class="instrument">
          <div class="topline">
            <span class="muted">${this.snapshot.phase ?? "Preparing measurement"}</span>
            <span class="connection ${this.connected ? "connected" : ""}" role="status">${this.connected ? "Live" : "Reconnecting"}</span>
          </div>
          <div class="value" aria-label="${Math.round(percent)} percent complete">${Math.round(percent)}<small>%</small></div>
          <progress max="100" .value=${percent}>${Math.round(percent)}%</progress>
          <div class="metrics">
            <div class="metric"><span>Mode</span><strong>${this.snapshot.mode ?? "—"}</strong></div>
            <div class="metric"><span>Variation</span><strong>${progress.completed} / ${progress.total}</strong></div>
            <div class="metric"><span>Remaining</span><strong>${this.remaining(progress.estimated_remaining_seconds)}</strong></div>
          </div>
          ${this.samples.length ? this.renderChart() : nothing}
        </div>
        ${this.snapshot.warnings?.length ? html`<div class="notice" role="status">${this.snapshot.warnings.at(-1)}</div>` : nothing}
        ${this.logs.length ? this.renderLog() : nothing}
        <div class="actions">
          ${this.snapshot.state === "awaiting_confirmation" ? html`<button class="primary" type="button" @click=${this.confirm} ?disabled=${this.busy}>Start measurement</button>` : nothing}
          <button class="danger" type="button" @click=${this.cancel} ?disabled=${this.busy || this.snapshot.state === "cancelling"}>${this.snapshot.state === "cancelling" ? "Cancelling…" : "Cancel measurement"}</button>
        </div>
      </section>
    `;
  }

  private renderChart() {
    const latest = this.samples.at(-1) ?? 0;
    const max = Math.max(...this.samples);
    const min = Math.min(...this.samples);
    const range = max - min || 1;
    const count = this.samples.length;
    const point = (watt: number, index: number): [number, number] => {
      const x = count === 1 ? 100 : (index / (count - 1)) * 100;
      const y = 30 - ((watt - min) / range) * 28; // 2..30 within a 32-high viewBox
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

  private renderLog() {
    return html`<div ${ref(this.logContainer)} class="log" aria-label="Recent measurement log" aria-live="polite">${this.logs.map((log) => this.logLine(log))}</div>`;
  }

  private logLine(log: string) {
    return html`<p>${log}</p>`;
  }

  private remaining(seconds?: number | null): string {
    if (seconds == null) return "Calculating";
    const minutes = Math.ceil(seconds / 60);
    return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
  }

  private cancel(): void {
    this.dispatchEvent(new CustomEvent("cancel", { bubbles: true, composed: true }));
  }

  private confirm(): void {
    this.dispatchEvent(new CustomEvent("confirm", { bubbles: true, composed: true }));
  }

  private runningTitle(): string {
    if (this.snapshot.state === "cancelling") return "Stopping safely";
    if (this.snapshot.state === "awaiting_confirmation") return "Ready when you are";
    return "Sampling in progress";
  }
}

customElements.define("measure-running-view", RunningView);
