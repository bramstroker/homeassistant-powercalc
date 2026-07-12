import { LitElement, css, html, nothing } from "lit";
import type { MeasurementRequest, PreflightResponse } from "../types";
import { sharedStyles } from "../styles";

export class PreflightView extends LitElement {
  static properties = {
    request: { attribute: false },
    preflight: { attribute: false },
    busy: { type: Boolean },
    errorMessage: { type: String },
    overwriteConfirmed: { type: Boolean },
  };

  request!: MeasurementRequest;
  preflight!: PreflightResponse;
  busy = false;
  errorMessage = "";
  overwriteConfirmed = false;

  static styles = [sharedStyles, css`
    .readout { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: var(--line); }
    .metric { padding: 1rem; background: #101519; }
    .metric span { display: block; color: var(--muted); font-size: 0.75rem; }
    .metric strong { display: block; margin-top: 0.35rem; font: 650 1rem/1.3 ui-monospace, monospace; }
    dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.6rem 1rem; }
    dt { color: var(--muted); } dd { margin: 0; overflow-wrap: anywhere; }
    .warning-list { padding-left: 1.25rem; }
    @media (max-width: 640px) { .readout { grid-template-columns: 1fr; } dl { grid-template-columns: 1fr; gap: 0.2rem; } dd { margin-bottom: 0.6rem; } }
  `];

  render() {
    const duration = this.preflight.estimated_duration_seconds;
    return html`
      <section class="panel" aria-labelledby="review-title">
        <p class="eyebrow">02 / Preflight</p>
        <h2 id="review-title">Ready for the bench</h2>
        <p class="muted">Powercalc checked entity availability, supported modes, and storage. Starting will begin controlling the selected light.</p>
        <div class="readout" aria-label="Measurement estimate">
          <div class="metric"><span>Variations</span><strong>${this.preflight.estimated_variations ?? "—"}</strong></div>
          <div class="metric"><span>Estimated time</span><strong>${duration === undefined ? "—" : this.duration(duration)}</strong></div>
          <div class="metric"><span>Modes</span><strong>${this.request.modes.length}</strong></div>
        </div>
        <dl>
          <dt>Model</dt><dd>${this.request.product_name} (${this.request.model_id})</dd>
          <dt>Light</dt><dd>${this.request.light_entity_id}</dd>
          <dt>Power</dt><dd>${this.request.power_entity_id}</dd>
          <dt>Modes</dt><dd>${this.request.modes.join(", ")}</dd>
        </dl>
        ${this.preflight.warnings.length ? html`
          <div class="notice"><strong>Check before starting</strong><ul class="warning-list">${this.preflight.warnings.map((warning) => html`<li>${warning}</li>`)}</ul></div>
        ` : nothing}
        ${this.request.resume_policy === "overwrite" ? html`
          <label><input type="checkbox" @change=${this.confirmOverwrite} /> I understand the previous measurement and its files will be deleted.</label>
        ` : nothing}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions">
          <button type="button" @click=${() => this.emit("back")}>Back</button>
          <button class="primary" type="button" @click=${() => this.emit("start")} ?disabled=${this.busy || (this.request.resume_policy === "overwrite" && !this.overwriteConfirmed)}>${this.busy ? "Starting…" : "Start measurement"}</button>
        </div>
      </section>
    `;
  }

  private duration(seconds: number): string {
    if (seconds < 60) return `${Math.ceil(seconds)} sec`;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.ceil((seconds % 3600) / 60);
    return hours ? `${hours} hr ${minutes} min` : `${minutes} min`;
  }

  private confirmOverwrite(event: Event): void {
    this.overwriteConfirmed = (event.currentTarget as HTMLInputElement).checked;
  }

  private emit(name: "back" | "start"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-preflight-view", PreflightView);
