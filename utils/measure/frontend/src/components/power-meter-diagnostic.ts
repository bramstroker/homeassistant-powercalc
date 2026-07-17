import { LitElement, css, html, nothing } from "lit";
import type { DiagnosticStatus, PowerMeterDiagnostic } from "../types";
import { sharedStyles } from "../styles";

export class PowerMeterDiagnosticView extends LitElement {
  static readonly properties = {
    diagnostic: { attribute: false },
    heading: { type: String },
  };

  diagnostic?: PowerMeterDiagnostic;
  heading = "Power meter quality";

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-width: 0; }
    .diagnostic { min-width: 0; overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: var(--field); }
    .diagnostic-header { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.8rem 0.9rem; border-bottom: 1px solid var(--line); }
    h4 { margin: 0; color: var(--ink); font-size: 0.9rem; }
    .status { flex: none; padding: 0.25rem 0.55rem; border: 1px solid currentColor; border-radius: 999px; font: 700 0.66rem/1 ui-monospace, monospace; letter-spacing: 0.05em; text-transform: uppercase; }
    .good { color: var(--good); }
    .warning { color: var(--signal-strong); }
    .poor { color: var(--danger); }
    .unsupported { color: var(--muted); }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); background: var(--line); gap: 1px; }
    .metric { min-width: 0; padding: 0.7rem 0.8rem; background: var(--field); }
    .metric span { display: block; color: var(--muted); font-size: 0.68rem; }
    .metric strong { display: block; overflow-wrap: anywhere; margin-top: 0.25rem; font: 650 0.86rem/1.3 ui-monospace, monospace; }
    .checks { display: grid; gap: 0.55rem; padding: 0.75rem 0.9rem; }
    .check { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; font-size: 0.78rem; }
    .check strong { text-align: right; }
    .messages { margin: 0; padding: 0 0.9rem 0.8rem 1.9rem; color: var(--muted); font-size: 0.76rem; line-height: 1.4; }
    .failure { margin: 0; padding: 0.75rem 0.9rem; color: var(--danger); font-size: 0.8rem; }
    @media (max-width: 700px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 520px) {
      .diagnostic-header, .check { align-items: flex-start; flex-direction: column; }
      .check { gap: 0.2rem; }
      .check strong { text-align: left; }
    }
  `];

  render() {
    const diagnostic = this.diagnostic;
    if (!diagnostic) return nothing;
    const messages = this.messages(diagnostic);
    return html`
      <section class="diagnostic" aria-label=${this.heading}>
        <div class="diagnostic-header">
          <h4>${this.heading}</h4>
          <span class="status ${diagnostic.status}">${this.statusLabel(diagnostic.status)}</span>
        </div>
        ${diagnostic.success
          ? this.renderReadings(diagnostic)
          : html`<p class="failure" role="alert">${diagnostic.message ?? "The measurement device could not be validated."}</p>`}
        ${messages.length ? this.renderMessages(messages) : nothing}
      </section>
    `;
  }

  private renderReadings(diagnostic: PowerMeterDiagnostic) {
    return html`
      <div class="metrics">
        ${this.metric("Current reading", diagnostic.power == null ? "—" : `${diagnostic.power} W`)}
        ${this.metric("Reported resolution", this.precision(diagnostic))}
        ${this.metric("Slowest update", this.interval(diagnostic))}
        ${this.metric("Reports observed", `${diagnostic.reports_observed} in ${diagnostic.duration_seconds.toFixed(0)} s`)}
      </div>
      <div class="checks">
        ${this.check("Reported resolution", diagnostic.precision_status)}
        ${this.check("Update frequency", diagnostic.update_interval_status)}
      </div>
    `;
  }

  private renderMessages(messages: string[]) {
    return html`
      <ul class="messages">
        ${messages.map((message) => html`<li>${message}</li>`)}
      </ul>
    `;
  }

  private metric(label: string, value: string) {
    return html`<div class="metric"><span>${label}</span><strong>${value}</strong></div>`;
  }

  private check(label: string, status: DiagnosticStatus) {
    return html`<div class="check"><span>${label}</span><strong class=${status}>${this.statusLabel(status)}</strong></div>`;
  }

  private precision(diagnostic: PowerMeterDiagnostic): string {
    if (diagnostic.precision_status === "unsupported" || diagnostic.precision_decimals == null) return "Not applicable";
    return `${diagnostic.precision_decimals} decimal${diagnostic.precision_decimals === 1 ? "" : "s"}`;
  }

  private interval(diagnostic: PowerMeterDiagnostic): string {
    if (diagnostic.update_interval_status === "unsupported") return "Direct polling";
    if (diagnostic.max_report_interval_seconds == null) return "Not observed";
    return `${diagnostic.max_report_interval_seconds.toFixed(1)} s`;
  }

  private messages(diagnostic: PowerMeterDiagnostic): string[] {
    return diagnostic.messages.filter((message) => message !== diagnostic.message);
  }

  private statusLabel(status: DiagnosticStatus): string {
    if (status === "good") return "Good";
    if (status === "warning") return "Acceptable";
    if (status === "poor") return "Needs attention";
    return "Not applicable";
  }
}

customElements.define("measure-power-meter-diagnostic", PowerMeterDiagnosticView);
