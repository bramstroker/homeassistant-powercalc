import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ErrorHelp, PlotCollection, SessionFile, SessionSnapshot, SessionState } from "../../types";
import { emit } from "../../utils/events";
import { fileSize } from "../../utils/format";
import { diagnosticsDownload, sharedStyles } from "../../styles";
import { errorHelpLink } from "../shared/error-help-link";
import "./plot";

const TROUBLESHOOTING_URL = "https://docs.powercalc.nl/contributing/measure/troubleshooting/";
const ZERO_READING_ERROR_PREFIX = "Aborting measurement session after repeated 0 W readings.";
const ANALYSIS_SUMMARY_LABELS = new Set([
  "Recording analysis",
  "Recording analysis reason",
  // Older sessions used these labels in their persisted summary.
  "Profile analysis",
  "Profile analysis reason",
  "Analysed feature",
  "Validation MAE",
  "Validation coverage",
]);
const INSPECTABLE_JSON_FILES = new Set(["analyser.json", "analysis.json", "model.json"]);

interface ResultOutcome {
  mark: string;
  title: string;
  description: string;
}

interface JsonInspectorState {
  name: string;
  content?: unknown;
  error?: string;
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
  @property({ attribute: false }) inspectJsonFile: (name: string) => Promise<unknown> = async () => undefined;
  @property({ type: String }) diagnosticsUrl = "";
  @property({ type: Boolean }) busy = false;
  @property({ type: Boolean }) canResume = false;
  @property({ type: Boolean }) canPrepareProfile = true;
  @property({ type: Boolean }) canAnalyse = false;
  @property({ type: Boolean }) analysisComplete = false;
  @property({ type: String }) errorMessage = "";
  @property({ attribute: false }) errorHelp?: ErrorHelp;

  @state() private jsonInspector?: JsonInspectorState;

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
    .analysis-panel { margin-top: 1.5rem; padding: clamp(1rem, 3vw, 1.35rem); border: 1px solid var(--line); border-radius: 14px; background: var(--well); }
    .analysis-panel h3 { margin: 0; font-size: 1.05rem; }
    .analysis-explanation { margin: 0.55rem 0 0; color: var(--muted); line-height: 1.55; }
    .analysis-explanation code { color: var(--ink); overflow-wrap: anywhere; }
    .analysis-outcome { display: flex; flex-wrap: wrap; gap: 0.4rem 0.75rem; align-items: baseline; margin: 1rem 0 0; }
    .analysis-outcome span { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .analysis-outcome strong { color: var(--signal-strong); font-size: 1.05rem; }
    .analysis-reason { margin: 0.7rem 0 0; color: var(--ink); line-height: 1.45; }
    .analysis-reason strong { color: var(--muted); }
    .analysis-details { display: flex; flex-wrap: wrap; gap: 0.65rem 1.5rem; margin: 1rem 0 0; padding-top: 0.85rem; border-top: 1px solid var(--line); }
    .analysis-details div { display: flex; flex-wrap: wrap; gap: 0.3rem 0.5rem; min-width: 0; align-items: baseline; }
    .analysis-details dt { display: inline-flex; align-items: center; gap: 0.3rem; color: var(--muted); font-size: 0.75rem; }
    .analysis-details dd { margin: 0; color: var(--ink); font-weight: 700; overflow-wrap: anywhere; }
    .analysis-help { position: relative; display: inline-grid; place-items: center; width: 1rem; height: 1rem; flex: 0 0 auto; border: 1px solid currentColor; border-radius: 50%; color: var(--muted); cursor: help; font: 700 0.65rem/1 sans-serif; }
    .analysis-help::after { position: absolute; z-index: 10; bottom: calc(100% + 0.5rem); left: 50%; width: min(16rem, calc(100vw - 2rem)); padding: 0.55rem 0.65rem; border: 1px solid var(--line); border-radius: 8px; background: var(--surface-raised); box-shadow: 0 8px 24px rgb(0 0 0 / 0.3); color: var(--ink); content: attr(data-help); font-size: 0.75rem; font-weight: 500; letter-spacing: normal; line-height: 1.4; opacity: 0; pointer-events: none; text-align: left; text-transform: none; transform: translate(-50%, 0.2rem); transition: opacity 120ms ease, transform 120ms ease; visibility: hidden; }
    .analysis-help:hover::after, .analysis-help:focus::after { opacity: 1; transform: translate(-50%, 0); visibility: visible; }
    .analysis-retry { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.75rem 1rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--line); }
    .analysis-retry p { flex: 1 1 30rem; margin: 0; color: var(--muted); font-size: 0.82rem; line-height: 1.45; }
    .analysis-retry p.complete { color: var(--good); font-weight: 700; }
    .files-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 1.5rem; }
    .files-header h3 { margin: 0; font-size: 1rem; }
    .download-all { min-height: 36px; padding: 0.45rem 0.75rem; border-radius: 999px; font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; }
    .file-actions { display: flex; align-items: center; gap: 0.55rem; }
    .inspect-file { display: grid; place-items: center; width: 38px; min-height: 38px; padding: 0; color: var(--signal-strong); }
    .inspect-file svg { width: 19px; height: 19px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
    .json-backdrop { position: fixed; z-index: 1000; inset: 0; display: grid; place-items: center; padding: clamp(1rem, 4vw, 3rem); background: rgb(0 0 0 / 0.72); }
    .json-dialog { display: grid; grid-template-rows: auto minmax(0, 1fr); width: min(900px, 100%); max-height: min(82vh, 900px); padding: 1rem; border: 1px solid var(--line); border-radius: 14px; background: var(--surface); box-shadow: 0 24px 80px rgb(0 0 0 / 0.45); }
    .json-dialog-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding-bottom: 0.8rem; }
    .json-dialog-header h3 { margin: 0; overflow-wrap: anywhere; }
    .json-dialog-header button { min-height: 38px; padding: 0.4rem 0.7rem; }
    .json-dialog pre { max-height: none; min-height: 12rem; white-space: pre; overflow-wrap: normal; overflow: auto; margin: 0; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); color: var(--ink); font-size: 0.75rem; line-height: 1.45; }
    .json-dialog .notice { margin: 0; }
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
        ${showArtifacts || this.canAnalyse ? this.renderAnalysis() : nothing}
        ${showArtifacts ? this.renderWarnings() : nothing}
        ${showArtifacts ? this.renderPlots() : nothing}
        ${showArtifacts ? this.renderFiles() : nothing}
        ${this.renderJsonInspector()}
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
          <li><span>${file.name}</span><small>${fileSize(file.size)}</small><div class="file-actions">
            ${this.isInspectableJson(file) ? html`
              <button class="inspect-file" type="button" title=${`View ${file.name}`} aria-label=${`View ${file.name}`} @click=${() => void this.openJsonInspector(file.name)}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.5"></circle></svg>
              </button>
            ` : nothing}
            <a href=${this.fileUrl(file.name)} download>Download<span class="sr-only"> ${file.name}</span></a>
          </div></li>
        `)}</ul>
      `;
    }
    if (this.summaryEntries().length) return nothing;
    return html`<p class="notice">No downloadable files are available for this session.</p>`;
  }

  private isInspectableJson(file: SessionFile): boolean {
    const basename = file.name.split("/").at(-1) ?? file.name;
    return file.media_type === "application/json" && INSPECTABLE_JSON_FILES.has(basename);
  }

  private async openJsonInspector(name: string): Promise<void> {
    this.jsonInspector = { name };
    try {
      const content = await this.inspectJsonFile(name);
      if (this.jsonInspector?.name === name) this.jsonInspector = { name, content };
    } catch (error) {
      if (this.jsonInspector?.name === name) {
        this.jsonInspector = { name, error: error instanceof Error ? error.message : "Could not load this file." };
      }
    }
  }

  private renderJsonInspector() {
    const inspector = this.jsonInspector;
    if (!inspector) return nothing;
    return html`
      <div class="json-backdrop" role="presentation" @click=${(event: MouseEvent) => {
        if (event.target === event.currentTarget) this.jsonInspector = undefined;
      }}>
        <section class="json-dialog" role="dialog" aria-modal="true" aria-labelledby="json-dialog-title">
          <div class="json-dialog-header">
            <h3 id="json-dialog-title">${inspector.name}</h3>
            <button type="button" autofocus @click=${() => { this.jsonInspector = undefined; }}>Close</button>
          </div>
          ${this.renderJsonInspectorContent(inspector)}
        </section>
      </div>
    `;
  }

  private renderJsonInspectorContent(inspector: JsonInspectorState) {
    if (inspector.error) return html`<p class="notice error" role="alert">${inspector.error}</p>`;
    if (inspector.content === undefined) return html`<p class="muted" role="status">Loading JSON…</p>`;
    return html`<pre>${JSON.stringify(inspector.content, null, 2)}</pre>`;
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
    const entries = this.summaryEntries().filter(([label]) => !ANALYSIS_SUMMARY_LABELS.has(label));
    if (!entries.length) return nothing;
    return html`<div class="readout" aria-label="Measurement result">
      ${entries.map(([label, value]) => html`<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)}
    </div>`;
  }

  private renderAnalysis() {
    const entries = this.summaryEntries().filter(([label]) => ANALYSIS_SUMMARY_LABELS.has(label));
    if (!entries.length && !this.canAnalyse) return nothing;
    const result = entries.find(([label]) => label === "Recording analysis")?.[1]
      ?? entries.find(([label]) => label === "Profile analysis")?.[1];
    const reason = entries.find(([label]) => label === "Recording analysis reason")?.[1]
      ?? entries.find(([label]) => label === "Profile analysis reason")?.[1];
    const feature = entries.find(([label]) => label === "Analysed feature")?.[1];
    const details = entries.filter(([label]) => !label.endsWith("analysis") && !label.endsWith("analysis reason"));
    return html`
      <section class="analysis-panel" aria-labelledby="recording-analysis-title">
        <h3 id="recording-analysis-title">Recording analysis</h3>
        <p class="analysis-explanation">
          ${feature
            ? html`PowerCalc analysed how the measured power changed for each value of <code>${this.analysisFeature(feature)}</code>. This creates a profile that can estimate power from that entity data.`
            : "PowerCalc compared the measured power with changes in the recorded entity states to create a suitable power profile."}
        </p>
        ${result ? html`<p class="analysis-outcome"><span>Result</span><strong>${this.analysisResult(result)}</strong></p>` : nothing}
        ${reason ? html`<p class="analysis-reason"><strong>Why:</strong> ${reason}</p>` : nothing}
        ${details.length ? html`<dl class="analysis-details" aria-label="Recording analysis details">
          ${details.map(([label, value]) => {
            const displayLabel = this.analysisDetailLabel(label);
            const help = this.analysisDetailHelp(label);
            return html`
              <div>
                <dt>
                  <span>${displayLabel}</span>
                  ${help ? html`<span class="analysis-help" tabindex="0" data-help=${help} title=${help} aria-label=${`${displayLabel}: ${help}`}>?</span>` : nothing}
                </dt>
                <dd>${label === "Analysed feature" ? this.analysisFeature(value) : value}</dd>
              </div>
            `;
          })}
        </dl>` : nothing}
        ${this.canAnalyse ? html`
          <div class="analysis-retry">
            <p class=${this.analysisComplete ? "complete" : ""} role=${this.analysisComplete ? "status" : nothing}>
              ${this.busy
                ? "Analysing the saved recording and refreshing the result…"
                : this.analysisComplete
                  ? "✓ Recording analysed again. The result and generated files are now up to date."
                  : html`Run the saved <code>record.jsonl</code> through the current analyser again. No new measurement is needed.`}
            </p>
            <button type="button" @click=${() => this.emit("analyse")} ?disabled=${this.busy}>
              ${this.busy ? "Analysing…" : "Analyse recording again"}
            </button>
          </div>
        ` : nothing}
      </section>
    `;
  }

  private analysisResult(result: string): string {
    if (result === "Fixed power profile created") return "A fixed power profile was created.";
    return result === "Fixed states_power model created" || result === "Fixed states_power profile created"
      ? "A state-based power profile was created."
      : result;
  }

  private analysisDetailLabel(label: string): string {
    if (label === "Analysed feature") return "Model input";
    if (label === "Validation MAE") return "Typical difference";
    if (label === "Validation coverage") return "Data coverage";
    return label;
  }

  private analysisDetailHelp(label: string): string | undefined {
    if (label === "Analysed feature") {
      return "The Home Assistant entity data that best explained the measured power changes. The generated profile will use this as its input.";
    }
    if (label === "Validation MAE") {
      return "How closely the profile matched measurement samples it had not used to learn. This is the typical difference in watts; lower is better.";
    }
    if (label === "Validation coverage") {
      return "The share of those measurement samples for which the profile could estimate power. 100% means every sample was covered.";
    }
    return undefined;
  }

  private analysisFeature(feature: string): string {
    return feature.endsWith(".state") ? feature.slice(0, -".state".length) : feature;
  }

  private renderWarnings() {
    return (this.snapshot.warnings ?? []).map((warning) => html`<p class="notice" role="status">${warning}</p>`);
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

  private emit(name: "sessions" | "new" | "resume" | "analyse" | "prepare"): void {
    emit(this, name);
  }
}
