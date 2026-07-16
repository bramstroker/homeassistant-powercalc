import { LitElement, css, html, nothing } from "lit";
import type { PowerMeterDiagnostic } from "../types";
import { sharedStyles } from "../styles";
import "./power-meter-diagnostic";

export interface ReviewMetric {
  label: string;
  value: string;
}

export interface ReviewRow {
  label: string;
  value: string;
}

export class PreflightView extends LitElement {
  static readonly properties = {
    title: { type: String },
    metrics: { attribute: false },
    summary: { attribute: false },
    warnings: { attribute: false },
    powerMeterDiagnostic: { attribute: false },
    canOverwrite: { type: Boolean },
    confirmationAction: { type: String },
    busy: { type: Boolean },
    errorMessage: { type: String },
    overwriteConfirmed: { type: Boolean },
  };

  title = "Ready for the bench";
  metrics: ReviewMetric[] = [];
  summary: ReviewRow[] = [];
  warnings: string[] = [];
  powerMeterDiagnostic?: PowerMeterDiagnostic | null;
  canOverwrite = false;
  confirmationAction = "";
  busy = false;
  errorMessage = "";
  overwriteConfirmed = false;

  static readonly styles = [sharedStyles, css`
    .readout { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 1px; overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: var(--line); margin-bottom: 1rem; }
    .metric { padding: 1rem; background: var(--field); }
    .metric span { display: block; color: var(--muted); font-size: 0.75rem; }
    .metric strong { display: block; margin-top: 0.35rem; font: 650 1rem/1.3 ui-monospace, monospace; }
    dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.6rem 1rem; }
    dt { color: var(--muted); } dd { margin: 0; overflow-wrap: anywhere; }
    .warning-list { padding-left: 1.25rem; }
    .starting { display: flex; align-items: center; gap: 0.8rem; margin-top: 1rem; }
    .starting-indicator { width: 22px; height: 22px; flex: none; border: 2px solid var(--line); border-top-color: var(--signal); border-radius: 50%; animation: spin 850ms linear infinite; }
    .starting strong, .starting span { display: block; }
    .starting span { margin-top: 0.2rem; color: var(--muted); font-size: 0.86rem; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 640px) { dl { grid-template-columns: 1fr; gap: 0.2rem; } dd { margin-bottom: 0.6rem; } }
    @media (prefers-reduced-motion: reduce) { .starting-indicator { animation: none; } }
  `];

  render() {
    return html`
      <section class="panel" aria-labelledby="review-title">
        <p class="eyebrow">02 / Setup check</p>
        <h2 id="review-title">${this.title}</h2>
        <p class="muted">${this.confirmationAction
          ? "Powercalc checked entity availability and storage. Preparing sets up the selected devices; you will explicitly start the measurement on the next screen."
          : "Powercalc checked entity availability and storage. Starting will begin controlling the selected device."}</p>
        ${this.metrics.length ? html`
          <div class="readout" aria-label="Measurement estimate">
            ${this.metrics.map((metric) => html`<div class="metric"><span>${metric.label}</span><strong>${metric.value}</strong></div>`)}
          </div>` : nothing}
        <dl>
          ${this.summary.map((row) => html`<dt>${row.label}</dt><dd>${row.value}</dd>`)}
        </dl>
        ${this.powerMeterDiagnostic ? html`<measure-power-meter-diagnostic heading="Measurement device quality" .diagnostic=${this.powerMeterDiagnostic}></measure-power-meter-diagnostic>` : nothing}
        ${this.warnings.length ? html`
          <div class="notice"><strong>Check before starting</strong><ul class="warning-list">${this.warnings.map((warning) => html`<li>${warning}</li>`)}</ul></div>
        ` : nothing}
        ${this.canOverwrite ? html`
          <label><input type="checkbox" @change=${this.confirmOverwrite} /> I understand the previous measurement and its files will be deleted.</label>
        ` : nothing}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        ${this.busy ? html`
          <div class="notice starting" role="status" aria-live="polite">
            <span class="starting-indicator" aria-hidden="true"></span>
            <span><strong>Initializing measurement session</strong><span>This can take a few seconds while Powercalc prepares the measurement devices.</span></span>
          </div>
        ` : nothing}
        <div class="actions">
          <button type="button" @click=${() => this.emit("back")} ?disabled=${this.busy}>Back</button>
          <button class="primary" type="button" @click=${() => this.emit("start")} ?disabled=${this.busy || (this.canOverwrite && !this.overwriteConfirmed)}>${this.busy ? "Preparing…" : this.confirmationAction ? "Prepare measurement" : "Start measurement"}</button>
        </div>
      </section>
    `;
  }

  private confirmOverwrite(event: Event): void {
    this.overwriteConfirmed = (event.currentTarget as HTMLInputElement).checked;
  }

  private emit(name: "back" | "start"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-preflight-view", PreflightView);
