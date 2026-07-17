import { LitElement, css, html, nothing, svg, type PropertyValues } from "lit";
import { createRef, ref } from "lit/directives/ref.js";
import type { OperatingPoint, SessionProgress, SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";

type StateChipIcon =
  | "battery"
  | "brightness"
  | "charging"
  | "color-temp"
  | "effect"
  | "fan-speed"
  | "hue"
  | "muted"
  | "not-charging"
  | "off"
  | "saturation"
  | "volume";

interface StateChip {
  label: string;
  icon: StateChipIcon;
}

export class RunningView extends LitElement {
  static readonly properties = {
    snapshot: { attribute: false },
    confirmationAction: { type: String },
    connected: { type: Boolean },
    logs: { attribute: false },
    samples: { attribute: false },
    diagnosticsUrl: { type: String },
    busy: { type: Boolean },
    logOpen: { state: true },
  };

  snapshot!: SessionSnapshot;
  confirmationAction = "";
  connected = false;
  logs: string[] = [];
  samples: number[] = [];
  diagnosticsUrl = "";
  busy = false;
  logOpen = false;
  private readonly logContainer = createRef<HTMLDivElement>();

  static readonly styles = [sharedStyles, css`
    .instrument { position: relative; overflow: hidden; background: var(--well); border: 1px solid var(--line); border-radius: 16px; padding: clamp(1.2rem, 4vw, 2rem); }
    .instrument::before { content: ""; position: absolute; inset: 0; opacity: 0.24; pointer-events: none; background: repeating-linear-gradient(90deg, transparent 0, transparent calc(10% - 1px), var(--grid) 10%); }
    .topline { position: relative; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
    .connection { display: inline-flex; align-items: center; gap: 0.45rem; color: var(--muted); font-size: 0.82rem; }
    .connection::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); }
    .connection.connected::before { background: var(--good); box-shadow: 0 0 0 4px color-mix(in srgb, var(--good) 16%, transparent); }
    .value { position: relative; margin: 0.9rem 0 1rem; font: 700 clamp(2.5rem, 7vw, 4rem)/1 "DIN Alternate", sans-serif; letter-spacing: -0.03em; color: var(--signal-strong); }
    .value small { margin-left: 0.3rem; font-size: 0.32em; font-weight: 650; letter-spacing: 0.04em; color: var(--muted); }
    progress { position: relative; display: block; width: 100%; height: 8px; border: 0; border-radius: 99px; overflow: hidden; appearance: none; }
    progress::-webkit-progress-bar { background: var(--track); } progress::-webkit-progress-value { background: var(--signal); } progress::-moz-progress-bar { background: var(--signal); }
    .metrics { position: relative; display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1.2rem; }
    .operating-point { position: relative; margin-top: 1.2rem; }
    .operating-point > span { display: block; margin-bottom: 0.55rem; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .state-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; }
    .state-chip { display: inline-flex; align-items: center; gap: 0.38rem; padding: 0.38rem 0.65rem; border: 1px solid var(--line); border-radius: 999px; background: color-mix(in srgb, var(--signal) 8%, var(--well)); font: 650 0.78rem/1 ui-monospace, monospace; color: var(--ink); }
    .state-icon { width: 14px; height: 14px; flex: none; color: var(--signal-strong); }
    .metric span { display: block; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric strong { display: block; margin-top: 0.25rem; font: 600 1rem/1.3 ui-monospace, monospace; }
    .topline-right { display: inline-flex; align-items: center; gap: 0.9rem; }
    .log-toggle { min-height: 30px; padding: 0.25rem 0.7rem; border-radius: 999px; font: 700 0.68rem/1 ui-monospace, monospace; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); background: transparent; }
    .log-toggle:hover:not(:disabled) { color: var(--ink); }
    .log-count { color: var(--signal-strong); }
    .log-overlay { position: fixed; top: 0; right: 0; bottom: 0; z-index: 60; display: flex; flex-direction: column; width: min(400px, 92vw); padding: 1rem; background: color-mix(in srgb, var(--surface) 96%, transparent); border-left: 1px solid var(--line); box-shadow: -18px 0 40px rgba(0, 0, 0, 0.4); backdrop-filter: blur(2px); }
    .log-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; }
    .log-head span { color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase; }
    .log-head button { min-height: 32px; padding: 0.3rem 0.6rem; }
    .log { flex: 1; overflow: auto; padding: 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); font: 0.8rem/1.6 ui-monospace, monospace; color: var(--muted); }
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
    .preparation { position: relative; display: grid; justify-items: center; gap: 0.8rem; padding: clamp(2rem, 8vw, 4rem) 1rem; text-align: center; }
    .preparation h3, .preparation p { margin: 0; }
    .preparation-spinner { width: 42px; height: 42px; border: 3px solid var(--track); border-top-color: var(--signal); border-radius: 50%; animation: spin 850ms linear infinite; }
    .preparation-track { position: relative; width: min(360px, 100%); height: 8px; margin-top: 0.4rem; overflow: hidden; border-radius: 99px; background: var(--track); }
    .preparation-bar { position: absolute; inset-block: 0; inset-inline-start: 0; width: 38%; border-radius: inherit; background: var(--signal); animation: prepare 1.35s ease-in-out infinite; }
    .ready-card { display: grid; justify-items: center; gap: 0.8rem; padding: clamp(1.5rem, 6vw, 3rem); border: 1px solid color-mix(in srgb, var(--good) 42%, var(--line)); border-radius: 16px; background: color-mix(in srgb, var(--good) 6%, var(--well)); text-align: center; }
    .ready-announcement { display: grid; justify-items: center; gap: 0.8rem; }
    .ready-announcement h3, .ready-announcement p { margin: 0; }
    .ready-icon { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 50%; background: color-mix(in srgb, var(--good) 16%, transparent); color: var(--good); font-size: 1.4rem; }
    .ready-message { max-width: 620px; color: var(--muted); line-height: 1.6; white-space: pre-line; }
    .ready-topline { display: flex; justify-content: flex-end; align-items: center; gap: 0.9rem; width: 100%; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes prepare { 0% { transform: translateX(-105%); } 50% { transform: translateX(165%); } 100% { transform: translateX(-105%); } }
    @media (max-width: 640px) { .metrics { grid-template-columns: 1fr 1fr; } .topline { align-items: flex-start; flex-direction: column; } }
    @media (prefers-reduced-motion: reduce) {
      .preparation-spinner, .preparation-bar { animation: none; }
      .preparation-bar { inset-inline-start: 31%; }
    }
  `];

  protected updated(changedProperties: PropertyValues<this>): void {
    if ((changedProperties.has("logs") || changedProperties.has("logOpen")) && this.logOpen && this.logs.length) {
      const container = this.logContainer.value;
      if (container) container.scrollTop = container.scrollHeight;
    }
  }

  render() {
    if (this.snapshot.state === "awaiting_confirmation") return this.renderReady();
    const preparing = !this.hasMeaningfulProgress();
    const progress = this.snapshot.progress ?? { completed: 0, total: 0 };
    const openEnded = this.snapshot.mode === "Recording" && (progress.total ?? 0) === 0;
    return html`
      <section class="panel" aria-labelledby="running-title">
        <p class="eyebrow">03 / Measurement</p>
        <h2 id="running-title">${this.runningTitle(preparing)}</h2>
        <div class="instrument">
          <div class="topline">
            <span class="muted" aria-live="polite">${this.snapshot.phase ?? "Preparing measurement"}</span>
            <span class="topline-right">
              ${this.logs.length ? html`<button class="log-toggle" type="button" @click=${this.toggleLog} aria-expanded=${this.logOpen}>Log <span class="log-count">${this.logs.length}</span></button>` : nothing}
              <span class="connection ${this.connected ? "connected" : ""}" role="status">${this.connected ? "Live" : "Reconnecting"}</span>
            </span>
          </div>
          ${preparing ? this.renderPreparation() : this.renderMeasurement(openEnded, progress)}
        </div>
        ${this.snapshot.warnings?.length ? html`<div class="notice" role="status">${this.snapshot.warnings.at(-1)}</div>` : nothing}
        ${this.logOpen && this.logs.length ? this.renderLog() : nothing}
        <div class="diagnostics-download">
          <span>Session snapshot and logs for issue reporting.</span>
          <a href=${this.diagnosticsUrl} download>Download diagnostics</a>
        </div>
        <div class="actions">
          ${this.renderStopButton(openEnded)}
        </div>
      </section>
    `;
  }

  private renderReady() {
    const message = this.snapshot.confirmation_message ?? "Preparation is complete. Start the measurement when the device is ready.";
    return html`
      <section class="panel" aria-labelledby="running-title">
        <p class="eyebrow">03 / Measurement</p>
        <h2 id="running-title">Ready when you are</h2>
        <div class="ready-card">
          <span class="ready-topline">
            ${this.logs.length ? html`<button class="log-toggle" type="button" @click=${this.toggleLog} aria-expanded=${this.logOpen}>Log <span class="log-count">${this.logs.length}</span></button>` : nothing}
            <span class="connection ${this.connected ? "connected" : ""}">${this.connected ? "Live" : "Reconnecting"}</span>
          </span>
          <div class="ready-announcement" role="status" aria-live="polite">
            <span class="ready-icon" aria-hidden="true">✓</span>
            <p class="eyebrow">Preparation complete</p>
            <h3>Everything is ready</h3>
            <p class="ready-message">${message}</p>
          </div>
          <button class="primary confirm" type="button" @click=${this.confirm} ?disabled=${this.busy}>${this.busy ? "Starting…" : this.confirmationAction || "Start measurement"}</button>
        </div>
        ${this.snapshot.warnings?.length ? html`<div class="notice" role="status">${this.snapshot.warnings.at(-1)}</div>` : nothing}
        ${this.logOpen && this.logs.length ? this.renderLog() : nothing}
        <div class="diagnostics-download">
          <span>Session snapshot and logs for issue reporting.</span>
          <a href=${this.diagnosticsUrl} download>Download diagnostics</a>
        </div>
        <div class="actions">${this.renderStopButton(false)}</div>
      </section>
    `;
  }

  private renderMeasurement(openEnded: boolean, progress: SessionProgress) {
    return html`
      ${this.renderProgress(openEnded, progress)}
      ${this.snapshot.operating_point ? this.renderOperatingPoint(this.snapshot.operating_point) : nothing}
      ${this.renderMetrics(openEnded, progress)}
      ${this.samples.length ? this.renderChart() : nothing}
    `;
  }

  private renderPreparation() {
    const phase = this.snapshot.phase ?? "Preparing measurement devices";
    return html`
      <div class="preparation" role="status" aria-live="polite">
        <span class="preparation-spinner" aria-hidden="true"></span>
        <h3>${phase}</h3>
        <p class="muted">Powercalc is getting everything ready. This can take a few seconds.</p>
        <span class="preparation-track" aria-hidden="true"><span class="preparation-bar"></span></span>
      </div>
      ${this.snapshot.operating_point ? this.renderOperatingPoint(this.snapshot.operating_point) : nothing}
      ${this.samples.length ? this.renderChart() : nothing}
    `;
  }

  private hasMeaningfulProgress(): boolean {
    const progress = this.snapshot.progress;
    if (!progress) return false;
    if (this.snapshot.mode === "Recording") return true;
    return progress.completed > 0 || progress.total > 0 || (progress.percent ?? 0) > 0;
  }

  private renderProgress(openEnded: boolean, progress: SessionProgress) {
    if (openEnded) {
      return html`<div class="value" aria-label="${progress.completed} samples recorded">${progress.completed}<small>samples</small></div>
                  <progress max="100" aria-label="Recording"></progress>`;
    }
    const percent = progress.percent ?? (progress.total ? progress.completed / progress.total * 100 : 0);
    return html`<div class="value" aria-label="${Math.round(percent)} percent complete">${Math.round(percent)}<small>%</small></div>
                <progress max="100" .value=${percent}>${Math.round(percent)}%</progress>`;
  }

  private renderMetrics(openEnded: boolean, progress: SessionProgress) {
    let progressLabel = "Variation";
    if (openEnded) progressLabel = "Recorded";
    else if (this.snapshot.mode === "Averaging" || this.snapshot.mode === "Trickle charging") progressLabel = "Seconds";
    else if (this.snapshot.mode === "Charging") progressLabel = "Battery";
    return html`
      <div class="metrics">
        <div class="metric"><span>Mode</span><strong>${this.snapshot.mode ?? "—"}</strong></div>
        <div class="metric"><span>${progressLabel}</span><strong>${openEnded ? progress.completed : html`${progress.completed} / ${progress.total}`}</strong></div>
        <div class="metric"><span>Remaining</span><strong>${openEnded ? "Until stopped" : this.remaining(progress.estimated_remaining_seconds)}</strong></div>
      </div>
    `;
  }

  private renderStopButton(openEnded: boolean) {
    const cancelling = this.snapshot.state === "cancelling";
    if (openEnded) {
      return html`<button class="primary" type="button" @click=${this.cancel} ?disabled=${this.busy || cancelling}>${cancelling ? "Stopping…" : "Stop recording"}</button>`;
    }
    return html`<button class="danger" type="button" @click=${this.cancel} ?disabled=${this.busy || cancelling}>${cancelling ? "Cancelling…" : "Cancel measurement"}</button>`;
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

  private renderOperatingPoint(point: OperatingPoint) {
    const chips = this.operatingPointChips(point);
    return html`
      <div class="operating-point" aria-live="polite">
        <span>Current measurement point</span>
        <div class="state-chips">
          ${chips.map((chip) => html`<span class="state-chip">${this.stateIcon(chip.icon)}${chip.label}</span>`)}
        </div>
      </div>
    `;
  }

  private operatingPointChips(point: OperatingPoint): StateChip[] {
    switch (point.type) {
      case "light":
        return this.lightChips(point);
      case "speaker":
        return [{ label: point.muted ? "Muted" : `Volume ${point.volume}%`, icon: point.muted ? "muted" : "volume" }];
      case "fan":
        return [{ label: point.on ? `Fan speed ${point.percentage}%` : "Off", icon: point.on ? "fan-speed" : "off" }];
      case "charging":
        return [
          { label: `Battery ${point.battery_level}%`, icon: "battery" },
          { label: point.charging ? "Charging" : "Not charging", icon: point.charging ? "charging" : "not-charging" },
        ];
    }
  }

  private lightChips(point: Extract<OperatingPoint, { type: "light" }>): StateChip[] {
    if (!point.on) return [{ label: "Off", icon: "off" }];
    const chips: StateChip[] = [];
    if (typeof point.brightness === "number") chips.push({ label: `Brightness ${Math.round(point.brightness / 255 * 100)}%`, icon: "brightness" });
    if (typeof point.color_temp_mired === "number") chips.push({ label: `Color temp ${Math.round(1_000_000 / point.color_temp_mired)} K`, icon: "color-temp" });
    if (typeof point.hue === "number") chips.push({ label: `Hue ${Math.round(point.hue / 65_535 * 360)}°`, icon: "hue" });
    if (typeof point.saturation === "number") chips.push({ label: `Saturation ${Math.round(point.saturation / 255 * 100)}%`, icon: "saturation" });
    if (point.effect) chips.push({ label: `Effect ${point.effect}`, icon: "effect" });
    return chips;
  }

  private stateIcon(icon: StateChipIcon) {
    const content = {
      battery: svg`<rect x="2" y="4.25" width="11" height="7.5" rx="1.25"></rect><path d="M14 6.5v3"></path><path d="M4 6.5h5"></path>`,
      brightness: svg`<circle cx="8" cy="8" r="2.25"></circle><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.4 1.4M11.55 11.55l1.4 1.4M12.95 3.05l-1.4 1.4M4.45 11.55l-1.4 1.4"></path>`,
      charging: svg`<path d="m9.2 1.8-5 7h3.3l-.7 5.4 5-7H8.5l.7-5.4Z"></path>`,
      "color-temp": svg`<path d="M6.2 9.5V3.3a1.8 1.8 0 0 1 3.6 0v6.2a3 3 0 1 1-3.6 0Z"></path><path d="M8 5v6"></path>`,
      effect: svg`<path d="m8 1 .8 3.2L12 5l-3.2.8L8 9l-.8-3.2L4 5l3.2-.8L8 1Z"></path><path d="m12.5 9 .45 1.55 1.55.45-1.55.45L12.5 13l-.45-1.55-1.55-.45 1.55-.45L12.5 9Z"></path>`,
      "fan-speed": svg`<circle cx="8" cy="8" r="1.15" fill="currentColor" stroke="none"></circle><path d="M8.5 6.9c.3-2.6 1.35-4.2 2.7-3.7 1.5.55 1.25 2.9-.15 4.25"></path><path d="M8.7 8.95c2.4 1.05 3.25 2.8 2.1 3.65-1.3.95-3.2-.45-3.7-2.3"></path><path d="M6.8 8.15c-2.1 1.55-4.05 1.4-4.25-.05-.2-1.6 1.95-2.55 3.8-2.05"></path>`,
      hue: svg`<circle cx="8" cy="8" r="5.5"></circle><path d="M8 2.5v3M13.5 8h-3M8 13.5v-3M2.5 8h3"></path>`,
      muted: svg`<path d="M2 6h2.5L8 3v10l-3.5-3H2V6Z"></path><path d="m11 6 3 4m0-4-3 4"></path>`,
      "not-charging": svg`<path d="m9.2 1.8-3 4.2M5 8H4.2l.55-.78M7.5 8h4.3l-2.25 3.15M8.8 12.2l-2 2 .28-2.2"></path><path d="m2 2 12 12"></path>`,
      off: svg`<path d="M8 1.5v6"></path><path d="M4.2 3.7a5.5 5.5 0 1 0 7.6 0"></path>`,
      saturation: svg`<path d="M8 1.5s4.5 5 4.5 8.2a4.5 4.5 0 1 1-9 0C3.5 6.5 8 1.5 8 1.5Z"></path><path d="M5.7 10.2c.25 1.1 1.05 1.65 2 1.8"></path>`,
      volume: svg`<path d="M2 6h2.5L8 3v10l-3.5-3H2V6Z"></path><path d="M10.5 5.5a3.5 3.5 0 0 1 0 5M12.5 3.5a6.2 6.2 0 0 1 0 9"></path>`,
    } satisfies Record<StateChipIcon, unknown>;
    return html`
      <svg class="state-icon" data-state-icon=${icon} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
        ${content[icon]}
      </svg>
    `;
  }

  private renderLog() {
    return html`
      <aside class="log-overlay" aria-label="Measurement log">
        <div class="log-head">
          <span>Measurement log</span>
          <button type="button" @click=${this.toggleLog} aria-label="Close log">Close ✕</button>
        </div>
        <div ${ref(this.logContainer)} class="log" aria-live="polite">${this.logs.map((log) => this.logLine(log))}</div>
      </aside>`;
  }

  private logLine(log: string) {
    return html`<p>${log}</p>`;
  }

  private toggleLog(): void {
    this.logOpen = !this.logOpen;
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

  private runningTitle(preparing = false): string {
    if (this.snapshot.state === "cancelling") return "Stopping safely";
    if (this.snapshot.state === "awaiting_confirmation") return "Ready when you are";
    if (preparing) return "Preparing measurement";
    return "Sampling in progress";
  }
}

customElements.define("measure-running-view", RunningView);
