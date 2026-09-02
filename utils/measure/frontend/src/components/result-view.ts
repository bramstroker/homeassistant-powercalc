import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ContributionAuthState, ContributionPreview, ContributionPreviewRequest, ContributionResult, ContributionSubmitRequest, ErrorHelp, PlotCollection, SessionFile, SessionSnapshot, SessionState, SettingsSection } from "../types";
import { emit } from "../events";
import { fileSize, words } from "../format";
import { formText } from "../form";
import { diagnosticsDownload, sharedStyles } from "../styles";
import { errorHelpLink } from "./error-help-link";
import "./result-plot";

const CONTRIBUTION_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/output/";
const TROUBLESHOOTING_URL = "https://docs.powercalc.nl/contributing/measure/troubleshooting/";
const PROFILE_LIBRARY_PATH = "profile_library/<manufacturer>/<model>/";
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

// Contribution methods. Add a new entry here (e.g. "local") to expose another way to
// contribute; renderMethodPanel routes the selected id to its panel renderer.
type ContributionMethodId = "github" | "manual" | "local";

interface ContributionMethod {
  id: ContributionMethodId;
  title: string;
  summary: string;
  available: boolean;
  unavailableReason?: string;
}

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
  @property({ attribute: false })
  snapshot!: SessionSnapshot;

  @property({ attribute: false })
  files: SessionFile[] = [];

  @property({ attribute: false })
  plotCollection: PlotCollection = { partial: false, plots: [], warnings: [] };

  @property({ attribute: false })
  fileUrl: (name: string) => string = () => "";

  @property({ attribute: false })
  downloadAll: () => void = () => {};

  @property({ type: String })
  diagnosticsUrl = "";

  @property({ type: Boolean })
  busy = false;

  @property({ type: Boolean })
  canResume = false;

  @property({ type: String })
  errorMessage = "";

  @property({ attribute: false })
  errorHelp?: ErrorHelp;

  @property({ attribute: false })
  contributionAuth?: ContributionAuthState;

  @property({ attribute: false })
  contributionDraft?: ContributionPreview;

  @property({ attribute: false })
  contributionPreview?: ContributionPreview;

  @property({ attribute: false })
  contributionResult?: ContributionResult;

  @property({ type: Boolean })
  contributionBusy = false;

  @property({ type: String })
  contributionError = "";

  @property({ type: String })
  contributionErrorField?: string;

  @state()
  contributionMethod?: ContributionMethodId;

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
    .analysis-explanation { max-width: 80ch; margin: 0.55rem 0 0; color: var(--muted); line-height: 1.55; }
    .analysis-explanation code { color: var(--ink); overflow-wrap: anywhere; }
    .analysis-outcome { display: flex; flex-wrap: wrap; gap: 0.4rem 0.75rem; align-items: baseline; margin: 1rem 0 0; }
    .analysis-outcome span { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .analysis-outcome strong { color: var(--signal-strong); font-size: 1.05rem; }
    .analysis-reason { margin: 0.7rem 0 0; color: var(--ink); line-height: 1.45; }
    .analysis-reason strong { color: var(--muted); }
    .analysis-details { display: flex; flex-wrap: wrap; gap: 0.65rem 1.5rem; margin: 1rem 0 0; padding-top: 0.85rem; border-top: 1px solid var(--line); }
    .analysis-details div { display: flex; flex-wrap: wrap; gap: 0.3rem 0.5rem; min-width: 0; align-items: baseline; }
    .analysis-details dt { color: var(--muted); font-size: 0.75rem; }
    .analysis-details dd { margin: 0; color: var(--ink); font-weight: 700; overflow-wrap: anywhere; }
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
    .contribution-methods { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin: 1.1rem 0; }
    .method-card { display: grid; gap: 0.35rem; padding: 0.85rem 0.95rem; border: 1px solid var(--line); border-radius: 12px; background: var(--well); text-align: left; cursor: pointer; }
    .method-card:hover:not(:disabled) { border-color: var(--signal); }
    .method-card.active { border-color: var(--signal); background: color-mix(in srgb, var(--signal) 12%, var(--well)); box-shadow: inset 0 0 0 1px var(--signal); }
    .method-card:disabled { cursor: default; opacity: 0.55; }
    .method-card strong { color: var(--ink); font-size: 0.95rem; }
    .method-card span { color: var(--muted); font-size: 0.8rem; }
    .method-flag { color: var(--signal-strong); font-size: 0.7rem; font-style: normal; text-transform: uppercase; letter-spacing: 0.08em; }
    .contribution-next ol { margin: 0 0 1rem; padding-left: 1.4rem; color: var(--ink); }
    .contribution-next li { display: list-item; padding: 0.25rem 0 0.25rem 0.2rem; border: 0; }
    .contribution-next code { color: var(--signal-strong); font-size: 0.88em; overflow-wrap: anywhere; }
    .contribution-guide { display: inline-flex; align-items: center; gap: 0.4rem; min-height: 40px; padding: 0.55rem 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--surface-raised); text-decoration: none; }
    .contribution-guide:hover { border-color: var(--signal); }
    .contribution-auto { padding: clamp(0.85rem, 3vw, 1.2rem); border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--field) 68%, transparent); }
    .contribution-form { display: grid; gap: 1rem; margin-top: 1rem; }
    .contribution-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.8rem; }
    .contribution-grid label, .notes-field { display: grid; gap: 0.35rem; }
    .contribution-grid span, .notes-field span, .preview-block span, .info-list span { color: var(--muted); font-size: 0.76rem; font-weight: 650; }
    input, textarea { background: var(--well); }
    textarea { min-height: 84px; resize: vertical; }
    .info-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.5rem 0.8rem; margin: 0; }
    .info-list div { min-width: 0; }
    .info-list dd { margin: 0.15rem 0 0; overflow-wrap: anywhere; }
    .preview-block { display: grid; gap: 0.45rem; min-width: 0; }
    pre { max-height: 240px; overflow: auto; margin: 0; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); color: var(--ink); font-size: 0.75rem; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
    .confirm-row { display: flex; align-items: flex-start; gap: 0.55rem; color: var(--muted); font-size: 0.82rem; }
    .confirm-row input { width: auto; margin-top: 0.2rem; }
    .success-link { display: inline-flex; margin-top: 0.75rem; color: var(--good); font-weight: 700; }
    .manufacturer-library-link { justify-self: start; font-size: 0.8rem; }
    .auth-shortcut { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; justify-content: space-between; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); }
    ul { list-style: none; margin: 0.65rem 0 0; padding: 0; border-top: 1px solid var(--line); }
    li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 1rem; padding: 0.8rem 0; border-bottom: 1px solid var(--line); }
    li span { overflow-wrap: anywhere; } li small { color: var(--muted); }
    a { color: var(--signal-strong); font-weight: 700; }
    @media (max-width: 520px) {
      .files-header { align-items: flex-start; flex-direction: column; }
      li { grid-template-columns: 1fr auto; }
      li small { grid-column: 1; grid-row: 2; }
      .contribution-grid { grid-template-columns: 1fr; }
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
        ${showArtifacts ? this.renderAnalysis() : nothing}
        ${showArtifacts ? this.renderWarnings() : nothing}
        ${showArtifacts ? this.renderPlots() : nothing}
        ${showArtifacts ? this.renderFiles() : nothing}
        ${showArtifacts ? this.renderContributionSection(state) : nothing}
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

  private renderError(error: string) {
    if (!error.includes(TROUBLESHOOTING_URL)) return error;
    const [before, after] = error.split(TROUBLESHOOTING_URL, 2);
    return html`${before}<a href=${TROUBLESHOOTING_URL} target="_blank" rel="noopener noreferrer">Troubleshooting guide</a>${after}`;
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

  private contributionMethods(): ContributionMethod[] {
    const draft = this.contributionPreview ?? this.contributionDraft;
    return [
      {
        id: "github",
        title: "GitHub pull request",
        summary: "Open a pull request to the shared Powercalc profile library, straight from here.",
        available: Boolean(draft?.eligible),
        unavailableReason: draft?.reason ?? "This session is not eligible for automatic contribution.",
      },
      {
        id: "manual",
        title: "Manual contribution",
        summary: "Download the generated files and open the pull request yourself.",
        available: true,
      },
      {
        id: "local",
        title: "Add to this installation",
        summary: "Use the measured profile directly in your local Powercalc setup.",
        available: false,
        unavailableReason: "Coming soon.",
      },
    ];
  }

  private selectedMethod(methods: ContributionMethod[]): ContributionMethodId {
    const chosen = methods.find((method) => method.id === this.contributionMethod && method.available);
    if (chosen) return chosen.id;
    return methods.find((method) => method.available)?.id ?? "manual";
  }

  private renderContributionSection(state: SessionSnapshot["state"]) {
    if (state !== "completed") return nothing;
    const methods = this.contributionMethods();
    const selected = this.selectedMethod(methods);
    return html`
      <section class="contribution" aria-labelledby="contribution-title">
        <p class="eyebrow">What's next?</p>
        <h3 id="contribution-title">Contribute your measurement</h3>
        <p class="muted">Choose how you want to add this device to Powercalc.</p>
        <div class="contribution-methods" role="radiogroup" aria-label="Contribution method">
          ${methods.map((method) => this.renderMethodCard(method, selected))}
        </div>
        ${this.renderMethodPanel(selected)}
      </section>
    `;
  }

  private renderMethodCard(method: ContributionMethod, selected: ContributionMethodId) {
    const active = method.id === selected;
    return html`
      <button
        type="button"
        role="radio"
        aria-checked=${active ? "true" : "false"}
        class="method-card ${active ? "active" : ""}"
        ?disabled=${!method.available}
        @click=${() => this.selectMethod(method.id)}
      >
        <strong>${method.title}</strong>
        <span>${method.summary}</span>
        ${method.available ? nothing : html`<em class="method-flag">${method.unavailableReason}</em>`}
      </button>
    `;
  }

  private selectMethod(id: ContributionMethodId): void {
    this.contributionMethod = id;
  }

  private renderMethodPanel(method: ContributionMethodId) {
    if (method === "github") return this.renderGithubPanel();
    if (method === "local") return this.renderLocalPanel();
    return this.renderManualPanel();
  }

  private renderManualPanel() {
    const firstStep = this.files.length
      ? "Download and inspect the generated files."
      : "Use the measured result above in a Powercalc profile.";
    return html`
      <div class="contribution-next">
        <ol>
          <li>${firstStep}</li>
          <li>Place the profile under <code>${PROFILE_LIBRARY_PATH}</code>.</li>
          <li>Open a pull request using the power profile template.</li>
        </ol>
        <a class="contribution-guide" href=${CONTRIBUTION_GUIDE_URL} target="_blank" rel="noopener noreferrer">
          Read the contribution guide <span aria-hidden="true">↗</span>
        </a>
      </div>
    `;
  }

  private renderLocalPanel() {
    return html`
      <div class="contribution-local">
        <p class="muted">Adding a measured profile directly to your local Powercalc installation is coming soon.</p>
      </div>
    `;
  }

  private renderGithubPanel() {
    const draft = this.contributionPreview ?? this.contributionDraft;
    if (!draft?.eligible) {
      return html`<div class="contribution-auto"><p class="muted">${draft?.reason ?? "This session is not eligible for automatic contribution."}</p></div>`;
    }
    return html`
      <div class="contribution-auto">
        ${this.renderContributionAuthShortcut()}
        <form class="contribution-form" @submit=${this.previewContribution}>
          <div class="contribution-grid">
            ${this.input("manufacturer_name", "Manufacturer name", draft.manufacturer_name)}
            ${this.input("manufacturer_directory", "Manufacturer directory", draft.manufacturer_directory, {
              required: false,
              placeholder: "Derived from the manufacturer when left empty",
            })}
            ${this.input("model_id", "Model ID", draft.model_id)}
            ${this.input("product_name", "Product name", draft.product_name, {
              hint: "Enter the marketed model name without repeating the manufacturer, for example “Hue White Ambiance GU10” rather than “Signify Hue White Ambiance GU10”.",
              error: this.contributionErrorField === "product_name" ? this.contributionError : "",
            })}
            ${this.input("contributor", "Contributor display", draft.contributor)}
          </div>
          ${draft.manufacturer_library_url
            ? html`<a class="manufacturer-library-link" href=${draft.manufacturer_library_url} target="_blank" rel="noopener noreferrer">View existing manufacturer profiles <span aria-hidden="true">↗</span></a>`
            : nothing}
          <label class="notes-field">
            <span>Notes</span>
            <textarea name="notes" .value=${draft.notes}></textarea>
          </label>
          ${this.renderDeviceInfo(draft)}
          <div class="actions">
            <button type="submit" ?disabled=${this.contributionBusy || !this.contributionAuth?.connected}>
              ${this.contributionBusy ? "Building preview…" : "Refresh preview"}
            </button>
          </div>
        </form>
        ${this.contributionPreview
          ? this.renderPreview(this.contributionPreview)
          : html`<p class="muted">Refresh the preview to validate the profile against the latest Powercalc library before confirming.</p>`}
        ${this.contributionError && this.contributionErrorField !== "product_name"
          ? html`<p class="notice error" role="alert">${this.contributionError}</p>`
          : nothing}
        ${this.renderContributionResult()}
      </div>
    `;
  }

  private renderContributionAuthShortcut() {
    if (this.contributionAuth?.connected) {
      const login = this.contributionAuth.identity?.login ?? "GitHub";
      return html`<p class="notice" role="status">Connected to GitHub as ${login}.</p>`;
    }
    return html`
      <div class="auth-shortcut">
        <span>Connect GitHub in settings before confirming an automatic contribution.</span>
        <button type="button" @click=${this.openGithubSettings}>Open GitHub settings</button>
      </div>`;
  }

  private renderDeviceInfo(draft: ContributionPreview) {
    return html`
      <dl class="info-list" aria-label="Contribution context">
        ${this.infoEntries("Device", draft.device_info)}
        ${this.infoEntries("Home Assistant", draft.home_assistant)}
      </dl>`;
  }

  private infoEntries(prefix: string, values: Record<string, string | number | boolean | null>) {
    return Object.entries(values).map(([label, value]) => html`
      <div><dt><span>${prefix} ${words(label)}</span></dt><dd>${value ?? "—"}</dd></div>
    `);
  }

  private renderPreview(preview: ContributionPreview) {
    return html`
      <div class="preview-block">
        <span>Repository</span>
        <pre>Upstream: ${preview.repository}
Fork: ${preview.fork_repository ?? "Created when submitted"}
Base: ${preview.base_branch}${preview.base_sha ? ` @ ${preview.base_sha}` : ""}
Branch: ${preview.branch_name}</pre>
      </div>
      <div class="preview-block">
        <span>Files</span>
        <pre>${preview.files.map((file) => `${file.path}\n${file.content ?? JSON.stringify(file.rendered_json ?? {}, null, 2)}`).join("\n\n")}</pre>
      </div>
      <div class="preview-block">
        <span>Rendered model JSON</span>
        <pre>${JSON.stringify(preview.model_json ?? preview.files.find((file) => file.path.endsWith("model.json"))?.rendered_json ?? {}, null, 2)}</pre>
      </div>
      <div class="preview-block">
        <span>Commit and pull request</span>
        <pre>${preview.commit_message}

${preview.pr_title}

${preview.pr_body}</pre>
      </div>
      ${preview.warnings.map((warning) => html`<p class="notice">${warning}</p>`)}
      <label class="confirm-row">
        <input name="confirm_contribution" type="checkbox" @change=${() => this.requestUpdate()} />
        <span>I reviewed the exact files, commit, and pull request text.</span>
      </label>
      <div class="actions">
        <button class="primary" type="button" @click=${this.submitContribution} ?disabled=${!this.canSubmitContribution()}>
          ${this.contributionBusy ? "Opening pull request…" : "Confirm and open PR"}
        </button>
      </div>
    `;
  }

  private renderContributionResult() {
    if (!this.contributionResult) return nothing;
    if (this.contributionResult.pull_request_url) {
      return html`<a class="success-link" href=${this.contributionResult.pull_request_url} target="_blank" rel="noopener noreferrer">View pull request</a>`;
    }
    return html`<p class="notice" role="status">${this.contributionResult.message ?? "Contribution is being processed."}</p>`;
  }

  private summaryEntries(): [string, string][] {
    return this.snapshot.summary ? Object.entries(this.snapshot.summary) : [];
  }

  private renderSummary() {
    const entries = this.summaryEntries().filter(([label]) => !ANALYSIS_SUMMARY_LABELS.has(label));
    if (!entries.length) return nothing;
    return html`<div class="readout" aria-label="Measurement result">
      ${entries.map(([label, value]) => html`
        <div class="metric">
          <span>${label}</span><strong>${value}</strong>
        </div>
      `)}
    </div>`;
  }

  private renderAnalysis() {
    const entries = this.summaryEntries().filter(([label]) => ANALYSIS_SUMMARY_LABELS.has(label));
    if (!entries.length) return nothing;
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
          ${details.map(([label, value]) => html`
            <div><dt>${this.analysisDetailLabel(label)}</dt><dd>${label === "Analysed feature" ? this.analysisFeature(value) : value}</dd></div>
          `)}
        </dl>` : nothing}
      </section>
    `;
  }

  private analysisResult(result: string): string {
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

  private analysisFeature(feature: string): string {
    return feature.endsWith(".state") ? feature.slice(0, -".state".length) : feature;
  }

  private renderWarnings() {
    const warnings = this.snapshot.warnings ?? [];
    return warnings.map((warning) => html`<p class="notice" role="status">${warning}</p>`);
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

  private input(
    name: keyof ContributionPreviewRequest,
    label: string,
    value: string,
    options: { required?: boolean; placeholder?: string; hint?: string; error?: string } = {},
  ) {
    const { required = true, placeholder = "", hint = "", error = "" } = options;
    return html`
      <label>
        <span>${label}</span>
        <input name=${name} .value=${value} ?required=${required} placeholder=${placeholder} autocomplete="off" aria-invalid=${error ? "true" : "false"} />
        ${hint ? html`<small class="field-hint">${hint}</small>` : nothing}
        ${error ? html`<small class="field-hint error" role="alert">${error}</small>` : nothing}
      </label>
    `;
  }

  private collectContribution(): ContributionPreviewRequest | null {
    const form = this.shadowRoot?.querySelector<HTMLFormElement>(".contribution-form");
    if (!form) return null;
    const data = new FormData(form);
    return {
      manufacturer_name: formText(data, "manufacturer_name"),
      manufacturer_directory: formText(data, "manufacturer_directory"),
      model_id: formText(data, "model_id"),
      product_name: formText(data, "product_name"),
      contributor: formText(data, "contributor"),
      notes: formText(data, "notes"),
    };
  }

  private previewContribution(event: SubmitEvent): void {
    event.preventDefault();
    const detail = this.collectContribution();
    if (!detail) return;
    emit<ContributionPreviewRequest>(this, "contribution-preview", detail);
  }

  private submitContribution(): void {
    const detail = this.collectContribution();
    if (!detail || !this.canSubmitContribution()) return;
    emit<ContributionSubmitRequest>(this, "contribution-submit", { ...detail, confirmed: true });
  }

  private canSubmitContribution(): boolean {
    const confirmed = this.shadowRoot?.querySelector<HTMLInputElement>('input[name="confirm_contribution"]')?.checked ?? false;
    return Boolean(confirmed && this.contributionAuth?.connected && !this.contributionBusy);
  }

  private openGithubSettings(): void {
    emit<{ section: SettingsSection }>(this, "open-settings", { section: "github" });
  }

  private emit(name: "sessions" | "new" | "resume"): void {
    emit(this, name);
  }
}
