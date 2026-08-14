import { LitElement, css, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { LabelledValue } from "../review-summary";
import type { PowerMeterDiagnostic } from "../types";
import { emit } from "../events";
import { sharedStyles } from "../styles";
import "./power-meter-diagnostic";

@customElement("measure-preflight-view")
export class PreflightView extends LitElement {
  @property({ type: String })
  title = "Ready for the bench";

  @property({ attribute: false })
  metrics: LabelledValue[] = [];

  @property({ attribute: false })
  summary: LabelledValue[] = [];

  @property({ attribute: false })
  warnings: string[] = [];

  @property({ attribute: false })
  powerMeterDiagnostic?: PowerMeterDiagnostic | null;

  @property({ type: String })
  confirmationAction = "";

  @property({ type: Boolean })
  busy = false;

  @property({ type: String })
  errorMessage = "";

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
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        ${this.busy ? html`
          <div class="notice starting" role="status" aria-live="polite">
            <span class="starting-indicator" aria-hidden="true"></span>
            <span><strong>Initializing measurement session</strong><span>This can take a few seconds while Powercalc prepares the measurement devices.</span></span>
          </div>
        ` : nothing}
        <div class="actions">
          <button type="button" @click=${() => this.emit("back")} ?disabled=${this.busy}>Back</button>
          <button class="primary" type="button" @click=${() => this.emit("start")} ?disabled=${this.busy}>${this.startButtonLabel()}</button>
        </div>
      </section>
    `;
  }

  private startButtonLabel(): string {
    if (this.busy) return "Preparing…";
    return this.confirmationAction ? "Prepare measurement" : "Start measurement";
  }

  private emit(name: "back" | "start"): void {
    emit(this, name);
  }
}
