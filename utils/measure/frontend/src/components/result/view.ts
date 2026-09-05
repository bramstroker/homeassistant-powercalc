import { LitElement, css, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ErrorHelp, PlotCollection, SessionFile, SessionSnapshot, SessionState } from "../../types";
import { emit } from "../../utils/events";
import { fileSize } from "../../utils/format";
import { diagnosticsDownload, sharedStyles } from "../../styles";
import { errorHelpLink } from "../shared/error-help-link";
import "./plot";

const TROUBLESHOOTING_URL = "https://docs.powercalc.nl/contributing/measure/troubleshooting/";
const ZERO_READING_ERROR_PREFIX = "Aborting measurement session after repeated 0 W readings.";

interface ResultOutcome {
  mark: string;
  title: string;
  description: string;
}

const COMPLETED: ResultOutcome = {
  mark: "✓",
  title: "Profile captured",
  description: "The complete output is ready to inspect or download.",
};

const COMPLETED_WITH_READOUT: ResultOutcome = {
  mark: "✓",
  title: "Measurement complete",
  description: "Here is the measured result.",
};

const CANCELLED: ResultOutcome = {
  mark: "↻",
  title: "Measurement cancelled",
  description: "Any complete output rows have been kept safely.",
};

/** Every terminal state a session can be shown in. Non-terminal states never reach this view. */
const OUTCOMES: Partial<Record<SessionState, ResultOutcome>> = {
  completed: COMPLETED,
  failed: {
    mark: "!",
    title: "Measurement stopped with an error",
    description: "Review the guidance below, correct the problem, and start a new measurement.",
  },
  resumable: {
    mark: "↻",
    title: "A measurement can be resumed",
    description: "Compatible output was found. Continue from the last complete variation.",
  },
  cancelled: CANCELLED,
};

@customElement("measure-result-view")
export class ResultView extends LitElement {
  @property({ attribute: false }) snapshot!: SessionSnapshot;
  @property({ attribute: false }) files: SessionFile[] = [];
  @property({ attribute: false }) plotCollection: PlotCollection = { partial: false, plots: [], warnings: [] };
  @property({ attribute: false }) fileUrl: (name: string) => string = () => "";
  @property({ attribute: false }) downloadAll: () => void = () => {};
  @property({ type: String }) diagnosticsUrl = "";
  @property({ type: Boolean }) busy = false;
  @property({ type: Boolean }) canResume = false;
  @property({ type: Boolean }) canPrepareProfile = true;
  @property({ type: String }) errorMessage = "";
  @property({ attribute: false }) errorHelp?: ErrorHelp;

  static readonly styles = [sharedStyles, css`
    .result-summary { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1rem; align-items: start; padding-bottom: 1.5rem; border-bottom: 1px solid var(--line); }
    .result-summary h2 { margin-bottom: 0.4rem; }
    .result-summary .muted { margin-bottom: 0; }
    .status-mark { display: grid; place-items: center; width: 48px; height: 48px; border: 1px solid var(--line); border-radius: 50%; color: var(--good); font: 700 1.3rem/1 ui-monospace, monospace; }
    .status-mark.failed { color: var(--danger); }
    .status-mark.cancelled, .status-mark.resumable { color: var(--signal); }
    .readout { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1px; overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: var(--line); margin-top: 1.5rem; }
    .metric { padding: 1rem; background: var(--field); }
    .metric span { display: block; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric strong { display: block; margin-top: 0.35rem; font: 700 1.4rem/1.1 "DIN Alternate", sans-serif; color: var(--signal-strong); }
    .files-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 1.5rem; }
    .files-header h3 { margin: 0; font-size: 1rem; }
    .download-all { min-height: 36px; padding: 0.45rem 0.75rem; border-radius: 999px; font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; }
    .plots-header { margin: 1.5rem 0 0.75rem; }
    .plots-header h3 { margin: 0; font-size: 1rem; }
    .plots { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 1rem; }
    .plot-warning { margin-top: 0.75rem; }
    .contribution { margin-top: 1.5rem; padding: clamp(1rem, 3vw, 1.35rem); border: 1px solid color-mix(in srgb, var(--signal) 48%, var(--line)); border-radius: 14px; background: color-mix(in srgb, var(--signal) 7%, var(--well)); }
    .contribution h3 { margin: 0 0 0.35rem; font-size: 1.15rem; }
    .contribution > p.muted { margin: 0; color: var(--muted); }
    ul { list-style: none; margin: 0.65rem 0 0; padding: 0; border-top: 1px solid var(--line); }
    li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 1rem; padding: 0.8rem 0; border-bottom: 1px solid var(--line); }
    li span { overflow-wrap: anywhere; }
    li small { color: var(--muted); }
    a { color: var(--signal-strong); font-weight: 700; }
    @media (max-width: 520px) {
      .files-header { align-items: flex-start; flex-direction: column; }
      li { grid-template-columns: 1fr auto; }
      li small { grid-column: 1; grid-row: 2; }
    }
  `];

  render() {
    const state = this.snapshot.state;
    const outcome = this.outcome(state);
    const error = typeof this.snapshot.error === "string" ? this.snapshot.error : this.snapshot.error?.message;
    const showArtifacts = state !== "failed";
    return html`
      <section class="panel" aria-labelledby="result-title">
        <p class="eyebrow">04 / Result</p>
        <div class="result-summary">
          <div class="status-mark ${state}" aria-hidden="true">${outcome.mark}</div>
          <div><h2 id="result-title">${outcome.title}</h2><p class="muted">${outcome.description}</p></div>
        </div>
        ${error ? html`<p class="notice error" role="alert">${this.renderError(error)}</p>` : nothing}
        ${showArtifacts ? this.renderSummary() : nothing}
        ${showArtifacts ? this.renderPlots() : nothing}
        ${showArtifacts ? this.renderFiles() : nothing}
        ${showArtifacts && state === "completed" && this.canPrepareProfile ? this.renderPrepareAction() : nothing}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}${errorHelpLink(this.errorHelp)}</p>` : nothing}
        ${diagnosticsDownload(this.diagnosticsUrl)}
        <div class="actions">
          <button type="button" @click=${() => this.emit("sessions")}>All sessions</button>
          <button type="button" @click=${() => this.emit("new")}>New measurement</button>
          ${this.renderResume(state)}
        </div>
      </section>
    `;
  }

  private renderPrepareAction() {
    return html`
      <section class="contribution" aria-labelledby="prepare-profile-title">
        <p class="eyebrow">What's next?</p>
        <h3 id="prepare-profile-title">Prepare the profile</h3>
        <p class="muted">Add product and measurement metadata, validate the result, and then download it or open a pull request.</p>
        <div class="actions"><button class="primary" type="button" @click=${() => this.emit("prepare")}>Prepare profile</button></div>
      </section>`;
  }

  private renderError(error: string) {
    if (!error.startsWith(ZERO_READING_ERROR_PREFIX)) return error;
    return html`
      Aborting measurement session after repeated 0 W readings. The power meter may not resolve this low load.
      Verify the device is on and connected, measure multiple identical lights together, add a resistive dummy load,
      or use a more sensitive meter. See
      <a href=${TROUBLESHOOTING_URL} target="_blank" rel="noopener noreferrer">Troubleshooting guide</a>
      for troubleshooting guidance.
    `;
  }

  private renderFiles() {
    if (this.files.length) {
      return html`
        <div class="files-header">
          <h3>Generated files</h3>
          <button class="download-all" type="button" @click=${() => this.downloadAll()}>Download all</button>
        </div>
        <ul>${this.files.map((file) => html`
          <li><span>${file.name}</span><small>${fileSize(file.size)}</small><a href=${this.fileUrl(file.name)} download>Download<span class="sr-only"> ${file.name}</span></a></li>
        `)}</ul>
      `;
    }
    if (this.summaryEntries().length) return nothing;
    return html`<p class="notice">No downloadable files are available for this session.</p>`;
  }

  private renderPlots() {
    const { plots, warnings, partial } = this.plotCollection;
    if (!plots.length && !warnings.length) return nothing;
    return html`
      ${plots.length ? html`
        <div class="plots-header"><h3>Result plots</h3></div>
        <div class="plots">
          ${plots.map((plot) => html`<measure-result-plot .plot=${plot} .partial=${partial}></measure-result-plot>`)}
        </div>
      ` : nothing}
      ${warnings.map((warning) => html`<p class="notice plot-warning">${warning}</p>`)}
    `;
  }

  private summaryEntries(): [string, string][] {
    return this.snapshot.summary ? Object.entries(this.snapshot.summary) : [];
  }

  private renderSummary() {
    const entries = this.summaryEntries();
    if (!entries.length) return nothing;
    return html`<div class="readout" aria-label="Measurement result">
      ${entries.map(([label, value]) => html`<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)}
    </div>`;
  }

  private renderResume(state: SessionState) {
    if (!this.canResume || (state !== "resumable" && state !== "cancelled")) return nothing;
    return html`<button class="primary" type="button" @click=${() => this.emit("resume")} ?disabled=${this.busy}>${this.busy ? "Resuming…" : "Resume measurement"}</button>`;
  }

  /** How this outcome is announced. A completed run reads differently with and without a readout. */
  private outcome(state: SessionState): ResultOutcome {
    if (state !== "completed") return OUTCOMES[state] ?? CANCELLED;
    return this.summaryEntries().length ? COMPLETED_WITH_READOUT : COMPLETED;
  }

  private emit(name: "sessions" | "new" | "resume" | "prepare"): void {
    emit(this, name);
  }
}
