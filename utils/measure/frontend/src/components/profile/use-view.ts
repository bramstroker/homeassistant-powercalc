import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type {
  ContributionAuthState,
  ContributionPreview,
  ContributionPreviewRequest,
  ContributionResult,
  ContributionSubmitRequest,
  SessionSnapshot,
  SettingsSection,
} from "../../types";
import { emit } from "../../events";
import { sharedStyles } from "../../styles";

const CONTRIBUTION_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/output/";
const PROFILE_LIBRARY_PATH = "profile_library/<manufacturer>/<model>/";

type ContributionMethodId = "github" | "manual" | "local";

interface ContributionMethod {
  id: ContributionMethodId;
  title: string;
  summary: string;
  available: boolean;
  unavailableReason?: string;
}

@customElement("measure-profile-use-view")
export class ProfileUseView extends LitElement {
  @property({ attribute: false }) snapshot!: SessionSnapshot;
  @property({ attribute: false }) preparedProfileUrl: (jobId: string) => string = () => "";
  @property({ attribute: false }) contributionAuth?: ContributionAuthState;
  @property({ attribute: false }) contributionDraft?: ContributionPreview;
  @property({ attribute: false }) contributionPreview?: ContributionPreview;
  @property({ attribute: false }) contributionResult?: ContributionResult;
  @property({ type: Boolean }) contributionBusy = false;
  @property({ type: String }) contributionError = "";

  @state()
  private contributionMethod?: ContributionMethodId;

  static readonly styles = [sharedStyles, css`
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
    .preview-block { display: grid; gap: 0.45rem; min-width: 0; }
    .preview-block span { color: var(--muted); font-size: 0.76rem; font-weight: 650; }
    pre { max-height: 240px; overflow: auto; margin: 0; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); color: var(--ink); font-size: 0.75rem; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
    .confirm-row { display: flex; align-items: flex-start; gap: 0.65rem; margin-top: 0.75rem; min-height: 44px; color: var(--muted); font-size: 0.82rem; line-height: 1.5; cursor: pointer; }
    .confirm-row input { flex: 0 0 1rem; width: 1rem; height: 1rem; min-height: 0; margin: 0.1rem 0 0; padding: 0; accent-color: var(--signal); cursor: pointer; }
    .confirm-row > span { min-width: 0; font-weight: 400; }
    .success-link { display: inline-flex; margin-top: 0.75rem; color: var(--good); font-weight: 700; }
    .auth-shortcut { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; justify-content: space-between; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); }
    a { color: var(--signal-strong); font-weight: 700; }
  `];

  render() {
    return html`
      <section class="panel" aria-labelledby="share-title">
        <p class="eyebrow">06 / Use profile</p>
        <h2 id="share-title">Choose how to use the profile</h2>
        <p class="muted">The enriched profile is validated and ready. Choose where it should go.</p>
        ${this.renderDeliverySection()}
        <div class="actions"><button type="button" @click=${() => emit(this, "back")}>Back to preparation</button></div>
      </section>`;
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

  private renderDeliverySection() {
    if (this.snapshot.state !== "completed") return nothing;
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
        @click=${() => { this.contributionMethod = method.id; }}
      >
        <strong>${method.title}</strong>
        <span>${method.summary}</span>
        ${method.available ? nothing : html`<em class="method-flag">${method.unavailableReason}</em>`}
      </button>`;
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
      </div>`;
  }

  private renderLocalPanel() {
    return html`<div class="contribution-local"><p class="muted">Adding a measured profile directly to your local Powercalc installation is coming soon.</p></div>`;
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
      </div>`;
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

  private renderGithubPreview(preview: ContributionPreview) {
    const baseRevision = preview.base_sha ? ` @ ${preview.base_sha}` : "";
    return html`
      <div class="preview-block">
        <span>Repository</span>
        <pre>Upstream: ${preview.repository}
Fork: ${preview.fork_repository ?? "Created when submitted"}
Base: ${preview.base_branch}${baseRevision}
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
      </div>`;
  }

  private renderContributionResult() {
    if (!this.contributionResult) return nothing;
    if (this.contributionResult.pull_request_url) {
      return html`<a class="success-link" href=${this.contributionResult.pull_request_url} target="_blank" rel="noopener noreferrer">View pull request</a>`;
    }
    return html`<p class="notice" role="status">${this.contributionResult.message ?? "Contribution is being processed."}</p>`;
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

  private submitContribution(): void {
    const detail = this.preparedContribution();
    if (!detail || !this.canSubmitContribution()) return;
    emit<ContributionSubmitRequest>(this, "contribution-submit", { ...detail, confirmed: true });
  }

  private canSubmitContribution(): boolean {
    const confirmed = this.shadowRoot?.querySelector<HTMLInputElement>('input[name="confirm_contribution"]')?.checked ?? false;
    return Boolean(confirmed && this.contributionPreview && this.contributionAuth?.connected && !this.contributionBusy);
  }

  private openGithubSettings(): void {
    emit<{ section: SettingsSection }>(this, "open-settings", { section: "github" });
  }
}
