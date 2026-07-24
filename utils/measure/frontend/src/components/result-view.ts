import { LitElement, css, html, nothing } from "lit";
import type { ContributionAuthState, ContributionPreview, ContributionPreviewRequest, ContributionResult, ContributionSubmitRequest, PlotCollection, SessionFile, SessionSnapshot, SettingsSection } from "../types";
import { sharedStyles } from "../styles";
import "./result-plot";

const CONTRIBUTION_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/output/";
const PROFILE_LIBRARY_PATH = "profile_library/<manufacturer>/<model>/";

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

export class ResultView extends LitElement {
  static readonly properties = {
    snapshot: { attribute: false },
    files: { attribute: false },
    plotCollection: { attribute: false },
    fileUrl: { attribute: false },
    downloadAll: { attribute: false },
    diagnosticsUrl: { type: String },
    busy: { type: Boolean },
    canResume: { type: Boolean },
    errorMessage: { type: String },
    contributionAuth: { attribute: false },
    contributionDraft: { attribute: false },
    contributionPreview: { attribute: false },
    contributionResult: { attribute: false },
    contributionBusy: { type: Boolean },
    contributionError: { type: String },
    contributionMethod: { state: true },
  };

  snapshot!: SessionSnapshot;
  files: SessionFile[] = [];
  plotCollection: PlotCollection = { partial: false, plots: [], warnings: [] };
  fileUrl: (name: string) => string = () => "";
  downloadAll: () => void = () => {};
  diagnosticsUrl = "";
  busy = false;
  canResume = false;
  errorMessage = "";
  contributionAuth?: ContributionAuthState;
  contributionDraft?: ContributionPreview;
  contributionPreview?: ContributionPreview;
  contributionResult?: ContributionResult;
  contributionBusy = false;
  contributionError = "";
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
    input, textarea {
      width: 100%; min-width: 0; border: 1px solid var(--line); border-radius: 9px;
      padding: 0.65rem 0.75rem; background: var(--well); color: var(--ink);
    }
    textarea { min-height: 84px; resize: vertical; }
    .info-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.5rem 0.8rem; margin: 0; }
    .info-list div { min-width: 0; }
    .info-list dd { margin: 0.15rem 0 0; overflow-wrap: anywhere; }
    .preview-block { display: grid; gap: 0.45rem; min-width: 0; }
    pre { max-height: 240px; overflow: auto; margin: 0; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); color: var(--ink); font-size: 0.75rem; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
    .confirm-row { display: flex; align-items: flex-start; gap: 0.55rem; color: var(--muted); font-size: 0.82rem; }
    .confirm-row input { width: auto; margin-top: 0.2rem; }
    .success-link { display: inline-flex; margin-top: 0.75rem; color: var(--good); font-weight: 700; }
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
    const error = typeof this.snapshot.error === "string" ? this.snapshot.error : this.snapshot.error?.message;
    return html`
      <section class="panel" aria-labelledby="result-title">
        <p class="eyebrow">04 / Result</p>
        <div class="result-summary">
          <div class="status-mark ${state}" aria-hidden="true">${this.statusMark(state)}</div>
          <div><h2 id="result-title">${this.resultTitle(state)}</h2><p class="muted">${this.description(state)}</p></div>
        </div>
        ${error ? html`<p class="notice error" role="alert">${error}</p>` : nothing}
        ${this.renderSummary()}
        ${this.renderPlots()}
        ${this.renderFiles()}
        ${this.renderContributionSection(state)}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="diagnostics-download">
          <span>Session snapshot and logs for issue reporting.</span>
          <a href=${this.diagnosticsUrl} download>Download diagnostics</a>
        </div>
        <div class="actions">
          <button type="button" @click=${() => this.emit("new")}>New measurement</button>
          ${this.renderResume(state)}
        </div>
      </section>
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
          <li><span>${file.name}</span><small>${this.size(file.size)}</small><a href=${this.fileUrl(file.name)} download>Download<span class="sr-only"> ${file.name}</span></a></li>
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
            ${this.input("product_name", "Product name", draft.product_name)}
            ${this.input("contributor", "Contributor display", draft.contributor)}
          </div>
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
        ${this.contributionError ? html`<p class="notice error" role="alert">${this.contributionError}</p>` : nothing}
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
      <div><dt><span>${prefix} ${this.label(label)}</span></dt><dd>${value ?? "—"}</dd></div>
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
    const entries = this.summaryEntries();
    if (!entries.length) return nothing;
    return html`<div class="readout" aria-label="Measurement result">
      ${entries.map(([label, value]) => html`<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)}
    </div>`;
  }

  private renderResume(state: SessionSnapshot["state"]) {
    if (!this.canResume || (state !== "resumable" && state !== "cancelled")) return nothing;
    return html`<button class="primary" type="button" @click=${() => this.emit("resume")} ?disabled=${this.busy}>${this.busy ? "Resuming…" : "Resume measurement"}</button>`;
  }

  private statusMark(state: SessionSnapshot["state"]): string {
    if (state === "completed") return "✓";
    if (state === "failed") return "!";
    return "↻";
  }

  private resultTitle(state: SessionSnapshot["state"]): string {
    if (state === "completed") return this.summaryEntries().length ? "Measurement complete" : "Profile captured";
    if (state === "failed") return "Measurement stopped with an error";
    if (state === "resumable") return "A measurement can be resumed";
    return "Measurement cancelled";
  }

  private description(state: SessionSnapshot["state"]): string {
    if (state === "completed") return this.summaryEntries().length ? "Here is the measured result." : "The complete output is ready to inspect or download.";
    if (state === "resumable") return "Compatible output was found. Continue from the last complete variation.";
    return "Any complete output rows have been kept safely.";
  }

  private size(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1_048_576).toFixed(1)} MB`;
  }

  private input(
    name: keyof ContributionPreviewRequest,
    label: string,
    value: string,
    options: { required?: boolean; placeholder?: string } = {},
  ) {
    const { required = true, placeholder = "" } = options;
    return html`<label><span>${label}</span><input name=${name} .value=${value} ?required=${required} placeholder=${placeholder} autocomplete="off" /></label>`;
  }

  private collectContribution(): ContributionPreviewRequest | null {
    const form = this.shadowRoot?.querySelector<HTMLFormElement>(".contribution-form");
    if (!form) return null;
    const data = new FormData(form);
    return {
      manufacturer_name: this.formString(data, "manufacturer_name"),
      manufacturer_directory: this.formString(data, "manufacturer_directory"),
      model_id: this.formString(data, "model_id"),
      product_name: this.formString(data, "product_name"),
      contributor: this.formString(data, "contributor"),
      notes: this.formString(data, "notes"),
    };
  }

  private formString(data: FormData, name: string): string {
    const value = data.get(name);
    return typeof value === "string" ? value.trim() : "";
  }

  private previewContribution(event: SubmitEvent): void {
    event.preventDefault();
    const detail = this.collectContribution();
    if (!detail) return;
    this.dispatchEvent(new CustomEvent<ContributionPreviewRequest>("contribution-preview", { detail, bubbles: true, composed: true }));
  }

  private submitContribution(): void {
    const detail = this.collectContribution();
    if (!detail || !this.canSubmitContribution()) return;
    this.dispatchEvent(new CustomEvent<ContributionSubmitRequest>("contribution-submit", {
      detail: { ...detail, confirmed: true },
      bubbles: true,
      composed: true,
    }));
  }

  private canSubmitContribution(): boolean {
    const confirmed = this.shadowRoot?.querySelector<HTMLInputElement>('input[name="confirm_contribution"]')?.checked ?? false;
    return Boolean(confirmed && this.contributionAuth?.connected && !this.contributionBusy);
  }

  private label(value: string): string {
    return value.replaceAll("_", " ");
  }

  private openGithubSettings(): void {
    this.dispatchEvent(new CustomEvent<{ section: SettingsSection }>("open-settings", { detail: { section: "github" }, bubbles: true, composed: true }));
  }

  private emit(name: "new" | "resume" | "open-settings"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-result-view", ResultView);
