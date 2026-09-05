import { LitElement, css, html, nothing, svg } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { SessionProgress, SessionSnapshot } from "../../types";
import { emit } from "../../events";
import { remaining } from "../../format";
import { diagnosticsDownload, sharedStyles } from "../../styles";
import "./chart";
import "./log";
import "./operating-point";

@customElement("measure-running-view")
export class RunningView extends LitElement {
  @property({ attribute: false })
  snapshot!: SessionSnapshot;

  @property({ type: String })
  confirmationAction = "";

  @property({ type: Boolean })
  warningConfirmation = false;

  @property({ type: Boolean })
  connected = false;

  @property({ attribute: false })
  logs: string[] = [];

  @property({ attribute: false })
  samples: number[] = [];

  @property({ type: String })
  diagnosticsUrl = "";

  @property({ type: Boolean })
  busy = false;

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
    .metric span { display: block; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric strong { display: block; margin-top: 0.25rem; font: 600 1rem/1.3 ui-monospace, monospace; }
    .topline-right { display: inline-flex; align-items: center; gap: 0.9rem; }
    .entity-states { position: relative; margin-top: 1.35rem; padding-top: 1rem; border-top: 1px solid var(--line); }
    .entity-states > span { display: block; margin-bottom: 0.65rem; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .entity-state-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 0.55rem; }
    .entity-state { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; min-width: 0; padding: 0.65rem 0.75rem; border: 1px solid var(--line); border-radius: 9px; background: color-mix(in srgb, var(--signal) 5%, var(--well)); }
    .entity-state code { overflow: hidden; color: var(--muted); font-size: 0.75rem; text-overflow: ellipsis; white-space: nowrap; }
    .entity-state strong { flex: none; font: 650 0.82rem/1.2 ui-monospace, monospace; color: var(--ink); }
    .preparation { position: relative; display: grid; justify-items: center; gap: 0.8rem; padding: clamp(2rem, 8vw, 4rem) 1rem; text-align: center; }
    .preparation h3, .preparation p { margin: 0; }
    .preparation-spinner { width: 42px; height: 42px; border: 3px solid var(--track); border-top-color: var(--signal); border-radius: 50%; animation: spin 850ms linear infinite; }
    .preparation-track { position: relative; width: min(360px, 100%); height: 8px; margin-top: 0.4rem; overflow: hidden; border-radius: 99px; background: var(--track); }
    .preparation-bar { position: absolute; inset-block: 0; inset-inline-start: 0; width: 38%; border-radius: inherit; background: var(--signal); animation: prepare 1.35s ease-in-out infinite; }
    .ready-card { display: grid; justify-items: center; gap: 0.8rem; padding: clamp(1.5rem, 6vw, 3rem); border: 1px solid color-mix(in srgb, var(--good) 42%, var(--line)); border-radius: 16px; background: color-mix(in srgb, var(--good) 6%, var(--well)); text-align: center; }
    .ready-card.warning { border-color: color-mix(in srgb, var(--warning) 58%, var(--line)); background: color-mix(in srgb, var(--warning) 8%, var(--well)); }
    .ready-announcement { display: grid; justify-items: center; gap: 0.8rem; }
    .ready-announcement h3, .ready-announcement p { margin: 0; }
    .ready-icon { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 50%; background: color-mix(in srgb, var(--good) 16%, transparent); color: var(--good); font-size: 1.4rem; }
    .ready-card.warning .ready-icon { width: 52px; height: 52px; border-radius: 14px; background: color-mix(in srgb, var(--warning) 15%, transparent); color: var(--warning); }
    .ready-card.warning .ready-icon svg { width: 34px; height: 34px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .ready-card.warning .ready-eyebrow { color: var(--warning); }
    .ready-message { max-width: 620px; color: var(--muted); line-height: 1.6; white-space: pre-line; }
    .ready-topline { display: flex; justify-content: flex-end; align-items: center; gap: 0.9rem; width: 100%; }
    @keyframes prepare { 0% { transform: translateX(-105%); } 50% { transform: translateX(165%); } 100% { transform: translateX(-105%); } }
    @media (max-width: 640px) { .metrics { grid-template-columns: 1fr 1fr; } .topline { align-items: flex-start; flex-direction: column; } }
    @media (prefers-reduced-motion: reduce) {
      .preparation-spinner, .preparation-bar { animation: none; }
      .preparation-bar { inset-inline-start: 31%; }
    }
  `];

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
            <span class="topline-right">${this.renderLog()}${this.renderConnection(true)}</span>
          </div>
          ${preparing ? this.renderPreparation() : this.renderMeasurement(openEnded, progress)}
        </div>
        ${this.renderFooter(openEnded)}
      </section>
    `;
  }

  /** Warnings, the log drawer, diagnostics and the stop control — the same on both screens. */
  private renderFooter(openEnded: boolean) {
    return html`
      ${this.renderLatestWarning()}
      ${diagnosticsDownload(this.diagnosticsUrl)}
      <div class="actions">${this.renderStopButton(openEnded)}</div>
    `;
  }

  private renderLog() {
    return html`<measure-session-log .logs=${this.logs} .warnings=${this.snapshot.warnings ?? []}></measure-session-log>`;
  }

  private renderConnection(announce: boolean) {
    return html`<span class="connection ${this.connected ? "connected" : ""}" role=${announce ? "status" : nothing}>
      ${this.connected ? "Live" : "Reconnecting"}
    </span>`;
  }

  private renderReady() {
    const message = this.snapshot.confirmation_message ?? "Preparation is complete. Start the measurement when the device is ready.";
    const warning = this.warningConfirmation;
    return html`
      <section class="panel" aria-labelledby="running-title">
        <p class="eyebrow">03 / Measurement</p>
        <h2 id="running-title">Ready when you are</h2>
        <div class="ready-card ${warning ? "warning" : ""}">
          <span class="ready-topline">${this.renderLog()}${this.renderConnection(false)}</span>
          <div class="ready-announcement" role=${warning ? "alert" : "status"} aria-live=${warning ? "assertive" : "polite"}>
            <span class="ready-icon" aria-hidden="true">${warning ? svg`
              <svg viewBox="0 0 24 24">
                <path d="M10.3 3.7 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z"></path>
                <path d="M12 9v4"></path><path d="M12 17h.01"></path>
              </svg>
            ` : "✓"}</span>
            <p class="eyebrow ready-eyebrow">${warning ? "High volume warning" : "Preparation complete"}</p>
            <h3>${warning ? "Protect your hearing" : "Everything is ready"}</h3>
            <p class="ready-message">${message}</p>
          </div>
          <button class="primary confirm" type="button" @click=${this.confirm} ?disabled=${this.busy}>${this.busy ? "Starting…" : this.confirmationAction || "Start measurement"}</button>
        </div>
        ${this.renderFooter(false)}
      </section>
    `;
  }

  private renderMeasurement(openEnded: boolean, progress: SessionProgress) {
    return html`
      ${this.renderProgress(openEnded, progress)}
      ${this.renderCalibrationSample()}
      ${this.snapshot.operating_point ? html`<measure-operating-point .point=${this.snapshot.operating_point}></measure-operating-point>` : nothing}
      ${this.renderMetrics(openEnded, progress)}
      ${this.samples.length ? html`<measure-power-chart .samples=${this.samples}></measure-power-chart>` : nothing}
      ${this.renderEntityStates()}
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
      ${this.snapshot.operating_point ? html`<measure-operating-point .point=${this.snapshot.operating_point}></measure-operating-point>` : nothing}
      ${this.samples.length ? html`<measure-power-chart .samples=${this.samples}></measure-power-chart>` : nothing}
      ${this.renderEntityStates()}
    `;
  }

  private renderEntityStates() {
    const states = Object.entries(this.snapshot.entity_states ?? {});
    if (!states.length) return nothing;
    return html`
      <div class="entity-states" aria-live="polite">
        <span>Tracked entities</span>
        <div class="entity-state-grid">
          ${states.map(([entityId, state]) => html`
            <div class="entity-state"><code title=${entityId}>${entityId}</code><strong>${state}</strong></div>
          `)}
        </div>
      </div>
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
    const percentLabel = percent > 0 && Math.round(percent) === 0 ? "<1" : String(Math.round(percent));
    return html`<div class="value" aria-label="${percentLabel} percent complete">${percentLabel}<small>%</small></div>
                <progress max="100" .value=${percent}>${percentLabel}%</progress>`;
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
        ${progress.skipped ? html`<div class="metric"><span>Skipped</span><strong>${progress.skipped}</strong></div>` : nothing}
        <div class="metric"><span>Remaining</span><strong>${openEnded ? "Until stopped" : remaining(progress.estimated_remaining_seconds)}</strong></div>
      </div>
    `;
  }

  private renderCalibrationSample() {
    const sample = this.snapshot.calibration_sample;
    const phase = `${this.snapshot.phase ?? ""} ${this.snapshot.mode ?? ""}`;
    if (!sample || !/dummy[- ]load/i.test(phase)) return nothing;
    return html`
      <div class="metrics calibration-metrics" aria-label="Live dummy-load calibration reading">
        <div class="metric"><span>Wattage</span><strong>${sample.power.toFixed(2)} W</strong></div>
        <div class="metric"><span>Resistance</span><strong>${sample.resistance.toFixed(2)} Ω</strong></div>
        <div class="metric"><span>Voltage</span><strong>${sample.voltage.toFixed(2)} V</strong></div>
      </div>
    `;
  }

  private renderStopButton(openEnded: boolean) {
    const cancelling = this.snapshot.state === "cancelling";
    const averaging = this.snapshot.mode === "Averaging" && this.snapshot.state !== "awaiting_confirmation";
    if (openEnded || averaging) {
      let label = "Stop measurement";
      if (cancelling) label = "Stopping…";
      else if (openEnded) label = "Stop recording";
      return html`<button class="primary" type="button" @click=${this.cancel} ?disabled=${this.busy || cancelling}>${label}</button>`;
    }
    return html`<button class="danger" type="button" @click=${this.cancel} ?disabled=${this.busy || cancelling}>${cancelling ? "Cancelling…" : "Cancel measurement"}</button>`;
  }

  private renderLatestWarning() {
    const warning = this.snapshot.warnings?.at(-1);
    return warning ? html`<div class="notice warning" role="alert">${warning}</div>` : nothing;
  }

  private cancel(): void {
    emit(this, "cancel");
  }

  private confirm(): void {
    emit(this, "confirm");
  }

  private runningTitle(preparing = false): string {
    if (this.snapshot.state === "cancelling") return "Stopping safely";
    if (this.snapshot.state === "awaiting_confirmation") return "Ready when you are";
    if (preparing) return "Preparing measurement";
    return "Sampling in progress";
  }
}
