import { LitElement, css, html, nothing } from "lit";
import type { PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { guard } from "lit/directives/guard.js";
import type { ContributionAuthState, ContributionDraft, ContributionPreview, ContributionPreviewRequest, ContributionResult, ContributionSubmitRequest, DeviceSpecificationField, ErrorHelp, PlotCollection, SessionFile, SessionSnapshot, SessionState, SettingsSection } from "../types";
import { emit } from "../events";
import { fileSize, words } from "../format";
import { formText } from "../form";
import { metadataLabels, validateMetadata } from "../profile-validation";
import type { ContributionFormValues } from "../types";
import { diagnosticsDownload, sharedStyles } from "../styles";
import { errorHelpLink } from "./error-help-link";
import "./result-plot";
import "./combobox";

const CONTRIBUTION_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/output/";
const TROUBLESHOOTING_URL = "https://docs.powercalc.nl/contributing/measure/troubleshooting/";
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

  @property({ attribute: false })
  preparedProfileUrl: (jobId: string) => string = () => "";

  @property({ type: String })
  diagnosticsUrl = "";

  @property({ type: Boolean })
  busy = false;

  @property({ type: Boolean })
  canResume = false;

  @property({ type: Boolean })
  canPrepareProfile = true;

  @property({ type: Boolean })
  profileMode = false;

  @property({ type: Boolean })
  shareMode = false;

  @property({ type: String })
  errorMessage = "";

  @property({ attribute: false })
  errorHelp?: ErrorHelp;

  @property({ attribute: false })
  contributionAuth?: ContributionAuthState;

  @property({ attribute: false })
  contributionDraft?: ContributionPreview;

  @property({ attribute: false })
  contributionFormValues: ContributionFormValues = {};

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

  @property({ attribute: false })
  manufacturers: string[] = [];

  @property({ attribute: false })
  measureDevices: string[] = [];

  @property({ type: Boolean })
  measureDevicesLoading = false;

  @property({ type: String })
  measureDevicesError = "";

  @property({ attribute: false })
  deviceSpecificationFields: Record<string, DeviceSpecificationField[]> = {};

  @state()
  contributionMethod?: ContributionMethodId;

  @state()
  contributionEdit?: ContributionPreviewRequest;

  @state()
  fieldErrors: Record<string, string> = {};

  @state()
  previewDirty = false;

  private dismissedServerField?: string;

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("snapshot") && changed.get("snapshot")?.session_id !== this.snapshot?.session_id) {
      if (this.hasUpdated) this.contributionFormValues = {};
      this.contributionEdit = undefined;
      this.fieldErrors = {};
      this.previewDirty = false;
      this.dismissedServerField = undefined;
    }
    if (changed.has("contributionPreview") && this.contributionPreview) {
      if (this.hasUpdated) this.contributionFormValues = {};
      this.contributionEdit = undefined;
      this.previewDirty = false;
      this.fieldErrors = {};
    }
    this.previewDirty = Object.keys(this.contributionFormValues).length > 0 || this.previewDirty;
    if (changed.has("contributionBusy") && this.contributionBusy) this.dismissedServerField = undefined;
  }

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has("contributionError") && this.contributionError && !this.shareMode) {
      this.focusValidation();
    }
  }

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
    .profile-metadata { padding: 0; border: 0; border-radius: 0; background: transparent; }
    .profile-guidance { max-width: 1000px; line-height: 1.55; }
    .contribution h3 { margin: 0 0 0.35rem; font-size: 1.15rem; }
    .contribution > p.muted { margin: 0; color: var(--muted); }
    .delivery-methods { margin-top: 1.25rem; padding-top: 1.25rem; border-top: 1px solid var(--line); }
    .delivery-methods > p.muted { margin: 0; }
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
    .contribution-form { display: grid; }
    .validation-footer { display: flex; align-items: center; justify-content: space-between; gap: 1.25rem; margin-top: 1.5rem; padding: 1rem 1.1rem; border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, var(--field) 72%, transparent); }
    .validation-status { margin: 0; color: var(--muted); line-height: 1.45; }
    .validation-status.pending { color: var(--ink); }
    .validation-status.valid { color: var(--good); font-weight: 650; }
    .validation-footer button { flex: 0 0 auto; }
    .validation-summary { margin: 0 0 1rem; }
    .validation-summary ul { display: block; margin: 0.5rem 0 0; padding-left: 1.25rem; }
    .validation-summary li { display: list-item; padding: 0.15rem 0; border: 0; }
    .validation-summary button { min-height: 0; padding: 0; border: 0; background: transparent; color: inherit; text-align: left; text-decoration: underline; font: inherit; }
    .required-guidance { margin: 0 0 1rem; font-size: 0.8rem; }
    .metadata-group { min-inline-size: 0; margin: 0; padding: 0; border: 0; border-top: 1px solid var(--line); }
    .metadata-group legend { padding: 0 0.65rem 0 0; color: var(--ink); font-size: 1rem; font-weight: 700; }
    .metadata-group-body { display: grid; gap: 0.8rem; padding: 0.75rem 0 1.5rem; }
    .profile-details { min-width: 0; }
    .profile-details summary { padding: 0.6rem 0; color: var(--muted); cursor: pointer; font-size: 0.82rem; }
    .profile-details summary:hover { color: var(--ink); }
    .profile-details-body { display: grid; gap: 1rem; padding: 0.5rem 0; }
    .prepared-preview { margin-top: 1rem; }
    .preparation-warning { margin: 1rem 0 0; }
    .metadata-group-description { margin: 0; color: var(--muted); font-size: 0.8rem; }
    .contribution-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.8rem; align-items: start; }
    .contribution-grid.contributor-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .contribution-grid > *, .contribution-grid label, .notes-field { align-self: start; }
    .contribution-grid label, .notes-field { display: grid; gap: 0.4rem; }
    .contribution-grid label > span, .notes-field > span { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    .field-stack { display: grid; gap: 0.4rem; min-width: 0; }
    .preview-block span, .info-list span { color: var(--muted); font-size: 0.76rem; font-weight: 650; }
    textarea { min-height: 84px; resize: vertical; }
    .info-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.5rem 0.8rem; margin: 0; }
    .info-list div { min-width: 0; }
    .info-list dd { margin: 0.15rem 0 0; overflow-wrap: anywhere; }
    .preview-block { display: grid; gap: 0.45rem; min-width: 0; }
    .schema-valid { border-left-color: var(--good); background: color-mix(in srgb, var(--good) 9%, transparent); }
    pre { max-height: 240px; overflow: auto; margin: 0; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); color: var(--ink); font-size: 0.75rem; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
    .confirm-row { display: flex; align-items: flex-start; gap: 0.65rem; margin-top: 0.75rem; min-height: 44px; color: var(--muted); font-size: 0.82rem; line-height: 1.5; cursor: pointer; }
    .confirm-row input { flex: 0 0 1rem; width: 1rem; height: 1rem; min-height: 0; margin: 0.1rem 0 0; padding: 0; accent-color: var(--signal); cursor: pointer; }
    .confirm-row > span { min-width: 0; font-weight: 400; }
    .success-link { display: inline-flex; margin-top: 0.75rem; color: var(--good); font-weight: 700; }
    .manufacturer-library-link { white-space: nowrap; }
    .auth-shortcut { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; justify-content: space-between; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); }
    ul { list-style: none; margin: 0.65rem 0 0; padding: 0; border-top: 1px solid var(--line); }
    li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 1rem; padding: 0.8rem 0; border-bottom: 1px solid var(--line); }
    li span { overflow-wrap: anywhere; } li small { color: var(--muted); }
    a { color: var(--signal-strong); font-weight: 700; }
    @media (max-width: 520px) {
      .files-header { align-items: flex-start; flex-direction: column; }
      li { grid-template-columns: 1fr auto; }
      li small { grid-column: 1; grid-row: 2; }
      .contribution-grid, .contribution-grid.contributor-grid { grid-template-columns: 1fr; }
      .validation-footer { align-items: stretch; flex-direction: column; }
      .validation-footer button { width: 100%; }
    }
  `];

  render() {
    const state = this.snapshot.state;
    const outcome = this.outcome(state);
    const error = typeof this.snapshot.error === "string" ? this.snapshot.error : this.snapshot.error?.message;
    const showArtifacts = state !== "failed";
    if (this.profileMode) {
      if (this.shareMode) {
        return html`
          <section class="panel" aria-labelledby="share-title">
            <p class="eyebrow">06 / Use profile</p>
            <h2 id="share-title">Choose how to use the profile</h2>
            <p class="muted">The enriched profile is validated and ready. Choose where it should go.</p>
            ${this.renderDeliverySection(state)}
            <div class="actions"><button type="button" @click=${() => this.emit("back")}>Back to preparation</button></div>
          </section>`;
      }
      return html`
        <section class="panel" aria-labelledby="profile-title">
          <p class="eyebrow">05 / Prepare</p>
          <h2 id="profile-title">Prepare your Powercalc profile</h2>
          <p class="muted profile-guidance">
            Review and enrich the metadata added to model.json.
            ${this.contributionPreview?.manufacturer_library_url ?? this.contributionDraft?.manufacturer_library_url
              ? html`Check the <a class="manufacturer-library-link" href=${this.contributionPreview?.manufacturer_library_url ?? this.contributionDraft?.manufacturer_library_url} target="_blank" rel="noopener noreferrer">existing manufacturer profiles <span aria-hidden="true">↗</span></a> and match the naming and metadata patterns used there.`
              : nothing}
          </p>
          ${this.renderPreparationSection(state)}
          <div class="actions"><button type="button" @click=${() => this.emit("back")}>Back to result</button></div>
        </section>`;
    }
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

  private renderPreparationSection(state: SessionSnapshot["state"]) {
    if (state !== "completed") return nothing;
    return html`
      <section class="contribution profile-metadata">
        ${this.renderPreparationPanel()}
      </section>
    `;
  }

  private renderDeliverySection(state: SessionSnapshot["state"]) {
    if (state !== "completed") return nothing;
    const methods = this.contributionMethods();
    const selected = this.selectedMethod(methods);
    return html`
      <section class="contribution profile-delivery" aria-labelledby="delivery-title">
        <h3 id="delivery-title">Available options</h3>
        <p class="muted">You can return to preparation without losing the validated metadata.</p>
        <div class="contribution-methods" role="radiogroup" aria-label="Profile delivery method">
          ${methods.map((method) => this.renderMethodCard(method, selected))}
        </div>
        ${this.renderMethodPanel(selected)}
      </section>`;
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
    const preview = this.contributionPreview;
    const downloadUrl = preview?.job_id ? this.preparedProfileUrl(preview.job_id) : "";
    return html`
      <div class="contribution-next">
        <ol>
          <li>${preview ? "The enriched profile is validated and ready." : "Validate the profile metadata before downloading it."}</li>
          <li>${downloadUrl
            ? html`<a href=${downloadUrl} download="powercalc-profile.zip">Download the prepared profile ZIP</a>.`
            : "A prepared ZIP becomes available after validation."}</li>
          <li>Extract it into a Powercalc checkout; it already contains <code>${PROFILE_LIBRARY_PATH}</code>.</li>
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
        ${this.contributionError ? html`<p class="notice error" role="alert">${this.contributionError}</p>` : nothing}
        ${this.contributionPreview
          ? this.renderGithubPreview(this.contributionPreview)
          : html`<p class="muted">Refresh the profile preview above before opening a pull request.</p>`}
        ${this.renderContributionResult()}
      </div>
    `;
  }

  private renderPreparationPanel() {
    const draft = this.editableDraft();
    if (!draft?.eligible) {
      return html`<div class="contribution-auto"><p class="muted">${draft?.reason ?? "This measurement cannot be prepared as a profile."}</p></div>`;
    }
    return html`
      <div class="contribution-auto">
        <form class="contribution-form" novalidate @submit=${this.previewContribution}
          @input=${this.metadataChanged} @change=${this.metadataChanged}
          @focusout=${this.validateField}
          @combobox-change=${this.metadataChanged}>
          ${this.renderValidationSummary()}
          <p class="muted required-guidance">Fields marked <span class="required-marker" aria-hidden="true">*</span><span class="sr-only">with an asterisk</span> are required.</p>
          <fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
            <legend>Product</legend>
            <div class="metadata-group-body">
              <p class="metadata-group-description">Identity and manufacturer details used to place and discover this profile.</p>
              <div class="contribution-grid">
                <div class="field-stack">
                  <measure-combobox
                    name="manufacturer_name"
                    label="Manufacturer"
                    .error=${this.fieldError("manufacturer_name")}
                    ?disabled=${this.contributionBusy}
                    .value=${this.fieldValue("manufacturer_name", draft.manufacturer_name)}
                    .options=${this.manufacturers.map((manufacturer) => ({ value: manufacturer, label: manufacturer }))}
                    placeholder="Search or enter a manufacturer"
                    hint="Choose an existing manufacturer or enter a new one."
                    required
                    allowCustom
                  >
                    <input slot="value" type="hidden" name="manufacturer_name" .value=${this.fieldValue("manufacturer_name", draft.manufacturer_name)} />
                  </measure-combobox>
                </div>
                ${this.input("model_id", "Model ID", draft.model_id)}
                ${this.input("product_name", "Product name", draft.product_name, {
                  hint: "Use the marketed name without repeating the manufacturer, e.g. “Hue White Ambiance GU10”.",
                })}
                ${this.input("product_url", "Manufacturer product URL", draft.product_url ?? "", { required: false, placeholder: "https://…" })}
                ${this.input("aliases", "Model aliases", (draft.aliases ?? []).join(", "), { required: false, placeholder: "Comma separated" })}
                ${this.input("gtins", "GTIN / barcodes", (draft.gtins ?? []).join(", "), { required: false, placeholder: "Comma separated" })}
              </div>
            </div>
          </fieldset>
          <fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
            <legend>Contributor</legend>
            <div class="metadata-group-body">
              <p class="metadata-group-description">These details are prefilled from your profile settings and credited in model.json.</p>
              <div class="contribution-grid contributor-grid">
                ${this.input("contributor", "Name", draft.contributor)}
                ${this.input("contributor_github", "GitHub username", draft.contributor_github ?? this.contributionAuth?.identity?.login ?? "")}
                ${this.input("contributor_email", "Email", draft.contributor_email ?? "", { required: false })}
              </div>
            </div>
          </fieldset>
          <fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
            <legend>Measurement</legend>
            <div class="metadata-group-body">
              <p class="metadata-group-description">Document the equipment and method used to create the profile.</p>
              <div class="contribution-grid">
                <div class="field-stack">
                  <measure-combobox
                    name="measure_device"
                    label="Measurement device"
                    .value=${this.fieldValue("measure_device", draft.measure_device)}
                    .options=${this.measureDevices.map((device) => ({ value: device, label: device }))}
                    .error=${this.fieldError("measure_device")}
                    ?disabled=${this.contributionBusy}
                    placeholder="e.g. Shelly Plug S"
                    .hint=${this.measureDevicesLoading
                      ? "Loading names used by existing Powercalc profiles…"
                      : "Choose an existing power meter or enter its manufacturer and model."}
                    required
                    allowCustom
                  >
                    <input slot="value" type="hidden" name="measure_device" .value=${this.fieldValue("measure_device", draft.measure_device)} />
                  </measure-combobox>
                  ${this.measureDevicesError
                    ? html`<small class="field-hint error" role="status">Library suggestions are unavailable; manual entry still works.</small>`
                    : nothing}
                </div>
                ${this.input("measure_device_firmware", "Device firmware", draft.measure_device_firmware ?? "", { required: false })}
                ${this.renderMainsVoltage(draft)}
              </div>
              <label class="notes-field">
                <span id="measure_description-label">Measurement description</span>
                <textarea name="measure_description" .value=${this.fieldValue("measure_description", draft.measure_description)}
                  aria-labelledby="measure_description-label"
                  aria-invalid=${this.fieldError("measure_description") ? "true" : "false"}
                  aria-describedby=${this.fieldError("measure_description") ? "measure_description-error" : nothing}></textarea>
                ${this.renderFieldError("measure_description")}
              </label>
            </div>
          </fieldset>
          ${this.renderDeviceSpecifications(draft)}
          <fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
            <legend>Contribution notes</legend>
            <div class="metadata-group-body">
              <p class="metadata-group-description">Optional context for reviewers; this is not added to model.json.</p>
              <label class="notes-field">
                <span id="notes-label">Notes</span>
                <textarea name="notes" .value=${this.fieldValue("notes", draft.notes)} aria-labelledby="notes-label" aria-invalid=${this.fieldError("notes") ? "true" : "false"}
                  aria-describedby=${this.fieldError("notes") ? "notes-error" : nothing}></textarea>
                ${this.renderFieldError("notes")}
              </label>
            </div>
          </fieldset>
          ${this.renderMeasurementContext(draft)}
          <div class="validation-footer">
            <p class=${`validation-status${this.canContinue() ? " valid" : this.previewDirty ? " pending" : ""}`} role="status">
              ${this.canContinue()
                ? html`<span aria-hidden="true">✓</span> Profile validated`
                : this.contributionBusy
                  ? "Checking your metadata and generated profile…"
                  : this.contributionError || Object.keys(this.fieldErrors).length
                    ? "Review the validation errors above, then validate again."
                    : this.previewDirty
                      ? "Your changes have not been validated yet."
                      : "Validate your metadata before continuing."}
            </p>
            ${this.canContinue()
              ? html`<button class="primary" type="button" @click=${() => { if (this.canContinue()) this.emit("share"); }}>Continue to use profile</button>`
              : html`<button class="primary" type="submit" ?disabled=${this.contributionBusy}>
                  ${this.contributionBusy ? "Validating profile…" : this.previewDirty ? "Validate changes" : "Validate profile"}
                </button>`}
          </div>
        </form>
        ${this.contributionPreview && this.canContinue()
          ? this.renderPreparedPreview(this.contributionPreview)
          : nothing}
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

  private renderMeasurementContext(draft: ContributionDraft) {
    const entries = Object.entries(draft.home_assistant).filter(([, value]) => value !== null && value !== "");
    if (!entries.length) return nothing;
    return html`
      <details class="profile-details">
        <summary>Measurement context</summary>
        <div class="profile-details-body">
          <dl class="info-list" aria-label="Home Assistant measurement context">
            ${entries.map(([label, value]) => html`<div><dt><span>Home Assistant ${words(label)}</span></dt><dd>${value}</dd></div>`)}
          </dl>
        </div>
      </details>`;
  }

  private renderMainsVoltage(draft: ContributionDraft) {
    if (draft.voltage_range) {
      return html`
        <label>
          <span>Nominal mains voltage</span>
          <input type="text" .value=${`${draft.mains_voltage ?? "—"} V`} readonly />
          <small class="field-hint">Calculated from the measured ${draft.voltage_range.min}–${draft.voltage_range.max} V range.</small>
        </label>`;
    }
    return html`
      <measure-combobox
        name="mains_voltage"
        label="Nominal mains voltage"
        .value=${this.fieldValue("mains_voltage", draft.mains_voltage)}
        .options=${[120, 230].map((voltage) => ({ value: String(voltage), label: `${voltage} V` }))}
        .error=${this.fieldError("mains_voltage")}
        ?disabled=${this.contributionBusy}
        placeholder="Select voltage"
        hint="The power meter did not report a voltage range, so select the nominal mains voltage used during measurement."
        required
      ></measure-combobox>`;
  }

  private renderDeviceSpecifications(draft: ContributionDraft) {
    const deviceType = this.deviceType(draft);
    const fields = deviceType ? (this.deviceSpecificationFields[deviceType] ?? []) : [];
    const typeLabel = deviceType ? optionLabel(deviceType) : "this device type";
    return html`
      <fieldset class="metadata-group" ?disabled=${this.contributionBusy}>
        <legend>Device specifications</legend>
        <div class="metadata-group-body">
          <p class="metadata-group-description">Optional manufacturer specifications for ${typeLabel.toLowerCase()} profiles.</p>
          ${fields.length
            ? html`<div class="contribution-grid">${fields.map((field) => this.renderDeviceSpecification(field, draft.device_specs?.[field.name]))}</div>`
            : html`<p class="muted">Specification fields are currently unavailable. Existing values will be kept.</p>`}
          ${this.renderFieldError("device_specs")}
        </div>
      </fieldset>`;
  }

  private renderDeviceSpecification(field: DeviceSpecificationField, value: unknown) {
    const name = `device_specs.${field.name}`;
    const error = this.fieldError(name);
    const describedBy = [field.description ? `${name}-hint` : "", error ? `${name}-error` : ""].filter(Boolean).join(" ");
    if (field.collection !== "scalar") {
      const selected = Array.isArray(value) ? value.map(String) : value === undefined || value === null ? [] : [String(value)];
      return html`
        <measure-combobox
          name=${name}
          label=${field.label}
          .error=${error}
          ?disabled=${this.contributionBusy}
          .value=${guard([value, this.contributionFormValues[name]], () => this.contributionFormValues[name] ?? selected)}
          .options=${field.options.map((option) => ({ value: option, label: optionLabel(option) }))}
          placeholder="Select an option…"
          hint=${field.description}
          multiple
        ></measure-combobox>`;
    }
    if (field.value_type === "boolean" || field.options.length) {
      const options = field.value_type === "boolean" ? ["true", "false"] : field.options;
      return html`
        <measure-combobox
          name=${name}
          label=${field.label}
          .value=${this.fieldValue(name, value)}
          .options=${[
            { value: "", label: "Not specified" },
            ...options.map((option) => ({
              value: option,
              label: field.value_type === "boolean" ? option === "true" ? "Yes" : "No" : optionLabel(option),
            })),
          ]}
          .error=${error}
          ?disabled=${this.contributionBusy}
          placeholder="Not specified"
          hint=${field.description}
        ></measure-combobox>`;
    }
    return html`
      <label>
        <span id=${`${name}-label`}>${field.name === "rated_power" ? "Rated power (W)" : field.name === "lumens" ? "Light output (lm)" : field.label}</span>
        <input
          name=${name}
          aria-labelledby=${`${name}-label`}
          aria-invalid=${error ? "true" : "false"}
          aria-describedby=${describedBy || nothing}
          type=${field.value_type === "number" || field.value_type === "integer" ? "number" : "text"}
          step=${field.value_type === "integer" ? "1" : field.value_type === "number" ? "any" : nothing}
          .value=${this.fieldValue(name, value)}
        />
        ${field.description ? html`<small id=${`${name}-hint`} class="field-hint">${field.description}</small>` : nothing}
        ${this.renderFieldError(name)}
      </label>`;
  }

  private renderPreparedPreview(preview: ContributionPreview) {
    return html`
      ${preview.warnings.map((warning) => html`<p class="notice warning preparation-warning">${warning}</p>`)}
      <details class="profile-details prepared-preview">
        <summary>Prepared files (${preview.files.length})</summary>
        <div class="profile-details-body">
          <div class="preview-block">
            <span>Files</span>
            <pre>${preview.files.map((file) => file.size === undefined ? file.path : `${file.path} (${fileSize(file.size)})`).join("\n")}</pre>
          </div>
          <div class="preview-block">
            <span>Generated model.json</span>
            <pre>${JSON.stringify(preview.model_json ?? preview.files.find((file) => file.path.endsWith("model.json"))?.rendered_json ?? {}, null, 2)}</pre>
          </div>
        </div>
      </details>
    `;
  }

  private renderGithubPreview(preview: ContributionPreview) {
    return html`
      <div class="preview-block">
        <span>Repository</span>
        <pre>Upstream: ${preview.repository}
Fork: ${preview.fork_repository ?? "Created when submitted"}
Base: ${preview.base_branch}${preview.base_sha ? ` @ ${preview.base_sha}` : ""}
Branch: ${preview.branch_name}</pre>
      </div>
      <div class="preview-block">
        <span>Commit and pull request</span>
        <pre>${preview.commit_message}

${preview.pr_title}

${preview.pr_body}</pre>
      </div>
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
    const { required = true, placeholder = "", hint = "" } = options;
    const error = options.error ?? this.fieldError(name);
    return html`
      <label>
        <span id=${`${name}-label`}>${label}${required ? html` <span class="required-marker" aria-hidden="true">*</span>` : nothing}</span>
        <input name=${name} type=${name === "contributor_email" ? "email" : "text"} .value=${this.fieldValue(name, value)} ?required=${required} placeholder=${placeholder} autocomplete="off" aria-invalid=${error ? "true" : "false"}
          aria-labelledby=${`${name}-label`}
          aria-describedby=${[hint ? `${name}-hint` : "", error ? `${name}-error` : ""].filter(Boolean).join(" ") || nothing} />
        ${hint ? html`<small id=${`${name}-hint`} class="field-hint">${hint}</small>` : nothing}
        ${error ? html`<small id=${`${name}-error`} class="field-hint error">${error}</small>` : nothing}
      </label>
    `;
  }

  private collectContribution(): ContributionPreviewRequest | null {
    const form = this.shadowRoot?.querySelector<HTMLFormElement>(".contribution-form");
    if (!form) return this.shareMode ? this.preparedContribution() : null;
    const data = new FormData(form);
    const draft = this.editableDraft();
    const fields = draft ? (this.deviceSpecificationFields[this.deviceType(draft)] ?? []) : [];
    const deviceSpecs = fields.length ? collectDeviceSpecifications(form, data, fields) : draft?.device_specs ?? null;
    const mainsVoltageControl = form.querySelector('measure-combobox[name="mains_voltage"]') as (HTMLElement & { value?: string }) | null;
    const mainsVoltageValue = formText(data, "mains_voltage")
      || (typeof mainsVoltageControl?.value === "string" ? mainsVoltageControl.value : "")
      || (draft?.mains_voltage === undefined || draft.mains_voltage === null ? "" : String(draft.mains_voltage));
    return {
      manufacturer_name: formText(data, "manufacturer_name"),
      model_id: formText(data, "model_id"),
      product_name: formText(data, "product_name"),
      contributor: formText(data, "contributor"),
      contributor_github: formText(data, "contributor_github"),
      contributor_email: formText(data, "contributor_email"),
      aliases: formList(data, "aliases"),
      gtins: formList(data, "gtins"),
      product_url: formText(data, "product_url"),
      mains_voltage: mainsVoltageValue ? Number(mainsVoltageValue) : null,
      device_specs: deviceSpecs,
      measure_device: formText(data, "measure_device"),
      measure_device_firmware: formText(data, "measure_device_firmware"),
      measure_description: formText(data, "measure_description"),
      notes: formText(data, "notes"),
    };
  }

  private preparedContribution(): ContributionPreviewRequest | null {
    const draft = this.contributionPreview;
    if (!draft) return null;
    return {
      manufacturer_name: draft.manufacturer_name,
      model_id: draft.model_id,
      product_name: draft.product_name,
      contributor: draft.contributor,
      contributor_github: draft.contributor_github ?? "",
      contributor_email: draft.contributor_email ?? "",
      aliases: draft.aliases ?? [],
      gtins: draft.gtins ?? [],
      product_url: draft.product_url ?? "",
      mains_voltage: draft.mains_voltage ?? null,
      device_specs: draft.device_specs ?? null,
      measure_device: draft.measure_device ?? "",
      measure_device_firmware: draft.measure_device_firmware ?? "",
      measure_description: draft.measure_description ?? "",
      notes: draft.notes,
    };
  }

  private previewContribution(event: SubmitEvent): void {
    event.preventDefault();
    if (this.contributionBusy) return;
    const detail = this.collectContribution();
    if (!detail) return;
    this.contributionEdit = detail;
    this.fieldErrors = validateMetadata(detail);
    const form = this.shadowRoot?.querySelector(".contribution-form");
    for (const input of form?.querySelectorAll<HTMLInputElement>('input[type="number"]') ?? []) {
      if (!input.validity.valid) this.fieldErrors[input.name] = input.validity.badInput ? "Enter a number." : "Enter a whole number.";
    }
    if (Object.keys(this.fieldErrors).length) {
      this.previewDirty = true;
      void this.updateComplete.then(() => this.focusValidation());
      return;
    }
    emit<ContributionPreviewRequest>(this, "contribution-preview", detail);
  }

  private submitContribution(): void {
    const detail = this.collectContribution();
    if (!detail || !this.canSubmitContribution()) return;
    emit<ContributionSubmitRequest>(this, "contribution-submit", { ...detail, confirmed: true });
  }

  private canSubmitContribution(): boolean {
    const confirmed = this.shadowRoot?.querySelector<HTMLInputElement>('input[name="confirm_contribution"]')?.checked ?? false;
    return Boolean(confirmed && this.contributionPreview && !this.previewDirty && this.contributionAuth?.connected && !this.contributionBusy);
  }

  private openGithubSettings(): void {
    emit<{ section: SettingsSection }>(this, "open-settings", { section: "github" });
  }

  private fieldError(name: string): string {
    return this.fieldErrors[name] ?? (this.contributionErrorField === name && this.dismissedServerField !== name ? this.contributionError : "");
  }

  private renderFieldError(name: string) {
    const error = this.fieldError(name);
    return error ? html`<small id=${`${name}-error`} class="field-hint error">${error}</small>` : nothing;
  }

  private validationErrors(): Record<string, string> {
    const errors = { ...this.fieldErrors };
    if (this.contributionError && this.dismissedServerField !== this.contributionErrorField) {
      errors[this.contributionErrorField ?? ""] = this.contributionError;
    } else if (this.contributionError && !this.contributionErrorField) errors[""] = this.contributionError;
    return errors;
  }

  private renderValidationSummary() {
    const errors = Object.entries(this.validationErrors());
    if (!errors.length) return nothing;
    return html`<div class="notice error validation-summary" role="alert" tabindex="-1">
      <strong>Check these profile details:</strong>
      <ul>${errors.map(([name, message]) => html`<li>${(name in metadataLabels && name !== "device_specs") || Object.values(this.deviceSpecificationFields).flat().some((field) => name === `device_specs.${field.name}`)
        ? html`<button type="button" @click=${() => this.focusField(name)}>${this.fieldLabel(name)}: ${message}</button>`
        : html`${message}`}</li>`)}</ul>
    </div>`;
  }

  private fieldLabel(name: string): string {
    const spec = Object.values(this.deviceSpecificationFields).flat().find((field) => `device_specs.${field.name}` === name);
    return metadataLabels[name] ?? spec?.label ?? words(name);
  }

  private fieldControl(name: string): HTMLElement | undefined {
    return Array.from(this.shadowRoot?.querySelectorAll<HTMLElement>("[name]") ?? [])
      .find((control) => control.getAttribute("name") === name && control.getAttribute("type") !== "hidden");
  }

  private focusField(name: string): void {
    const control = this.fieldControl(name);
    const input = control?.shadowRoot?.querySelector<HTMLElement>("input, select") ?? control;
    input?.focus();
    input?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }

  private focusValidation(): void {
    const first = Object.keys(this.validationErrors()).find((name) => this.fieldControl(name));
    if (first) this.focusField(first);
    else {
      const summary = this.shadowRoot?.querySelector<HTMLElement>(".validation-summary");
      summary?.focus();
      summary?.scrollIntoView?.({ block: "center" });
    }
  }

  private metadataChanged(event: Event): void {
    const control = event.target as HTMLElement & { name?: string; value?: string | string[] };
    const name = control.name;
    if (!name || name === "confirm_contribution") return;
    if (control.value !== undefined) {
      this.contributionFormValues = { ...this.contributionFormValues, [name]: control.value };
      emit(this, "contribution-edit", this.contributionFormValues);
    }
    this.previewDirty = true;
    const errors = { ...this.fieldErrors };
    delete errors[name];
    this.fieldErrors = errors;
    if (this.contributionErrorField === name) this.dismissedServerField = name;
  }

  private fieldValue(name: string, fallback: unknown): string {
    const value = this.contributionFormValues[name] ?? fallback;
    return value === undefined || value === null ? "" : String(value);
  }

  private validateField(event: FocusEvent): void {
    const control = event.target as HTMLElement & { name?: string };
    const name = control.name;
    if (!name || this.contributionBusy || event.relatedTarget === control || control.contains(event.relatedTarget as Node | null)) return;
    const values = this.collectContribution();
    if (!values) return;
    const validation = validateMetadata(values);
    const errors = { ...this.fieldErrors };
    for (const field of name === "manufacturer_name" ? [name, "product_name"] : [name]) {
      if (validation[field]) errors[field] = validation[field];
      else delete errors[field];
    }
    this.fieldErrors = errors;
  }

  private canContinue(): boolean {
    return Boolean(this.contributionPreview && !this.previewDirty && !this.contributionBusy && !this.contributionError && !Object.keys(this.fieldErrors).length);
  }

  private editableDraft(): ContributionDraft | undefined {
    const source = this.contributionPreview ?? this.contributionDraft;
    return source && this.contributionEdit ? { ...source, ...this.contributionEdit } : source;
  }

  private deviceType(draft: ContributionDraft): string {
    if (draft.device_type) return draft.device_type;
    if (typeof draft.model_json !== "object" || draft.model_json === null || Array.isArray(draft.model_json)) return "";
    const value = (draft.model_json as Record<string, unknown>).device_type;
    return typeof value === "string" ? value : "";
  }

  private emit(name: "sessions" | "new" | "resume" | "prepare" | "share" | "back"): void {
    emit(this, name);
  }
}

function formList(data: FormData, name: string): string[] {
  return formText(data, name).split(",").map((value) => value.trim()).filter(Boolean);
}

function collectDeviceSpecifications(form: HTMLFormElement, data: FormData, fields: DeviceSpecificationField[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const name = `device_specs.${field.name}`;
    if (field.collection !== "scalar") {
      const control = Array.from(form.querySelectorAll("measure-combobox"))
        .find((candidate) => candidate.multiple && candidate.name === name);
      const controlValues = Array.isArray(control?.value) ? control.value : [];
      const values = (data.getAll(name).length ? data.getAll(name).map(String) : controlValues).filter(Boolean);
      if (!values.length) continue;
      result[field.name] = field.collection === "scalar_or_array" && values.length === 1 ? values[0] : values;
      continue;
    }
    const control = Array.from(form.querySelectorAll("measure-combobox"))
      .find((candidate) => !candidate.multiple && candidate.name === name);
    const value = formText(data, name) || (typeof control?.value === "string" ? control.value : "");
    if (!value) continue;
    if (field.value_type === "number" || field.value_type === "integer") result[field.name] = Number(value);
    else if (field.value_type === "boolean") result[field.name] = value === "true";
    else result[field.name] = value;
  }
  return result;
}

function optionLabel(value: string): string {
  const abbreviations: Record<string, string> = {
    rf433: "RF 433",
    usb: "USB",
    wifi: "Wi-Fi",
    zwave: "Z-Wave",
  };
  if (abbreviations[value]) return abbreviations[value];
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
