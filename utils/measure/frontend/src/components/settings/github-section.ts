import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ContributionAuthDeviceStatus, ContributionAuthState, ContributionDeviceFlow } from "../../types";
import { emit } from "../../events";

@customElement("measure-settings-github-section")
export class SettingsGithubSection extends LitElement {
  @property({ attribute: false }) auth?: ContributionAuthState;
  @property({ attribute: false }) deviceFlow?: ContributionDeviceFlow;
  @property({ attribute: false }) deviceStatus?: ContributionAuthDeviceStatus;
  @property({ type: Boolean }) busy = false;
  @property({ type: String }) errorMessage = "";

  @state()
  private copyStatus = "";

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  render() {
    return html`
      <div class="section-fields">
        <div class="github-card">
          ${this.auth?.connected ? this.renderIdentity() : this.renderConnect()}
        </div>
        ${this.auth?.connected ? nothing : this.renderTokenFallback()}
        <p class="notice">GitHub credentials are stored by the measure app and can be included in Home Assistant backups. Disconnect GitHub before sharing or exporting backups you do not control.</p>
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
      </div>
    `;
  }

  private renderIdentity() {
    const permissionsHint = this.auth?.permissions_verified === false
      ? html`<span class="field-hint">Identity verified. Fine-grained token permissions can only be confirmed during submission.</span>`
      : nothing;
    return html`
      <div class="identity">
        <div>
          <span class="field-hint">Connected as</span>
          <strong>${this.auth?.identity?.login ?? "GitHub"}</strong>
          ${permissionsHint}
        </div>
        <button class="danger" type="button" @click=${this.disconnect} ?disabled=${this.busy}>Disconnect</button>
      </div>
    `;
  }

  private renderConnect() {
    const deviceFlowHint = this.auth?.device_flow_available === false
      ? html`<p class="field-hint">Device login is not configured for this app build. Use a personal access token.</p>`
      : nothing;
    return html`
      <p class="muted">Connect GitHub to contribute measured profiles. You only need to do this once.</p>
      ${this.renderDeviceFlow()}
      ${deviceFlowHint}
    `;
  }

  private renderDeviceFlow() {
    if (!this.deviceFlow) {
      return html`
        <button
          type="button"
          @click=${this.startDeviceLogin}
          ?disabled=${this.busy || this.auth?.device_flow_available === false}
        >
          ${this.busy ? "Starting…" : "Connect GitHub"}
        </button>
      `;
    }
    if (this.deviceStatus?.status === "expired" || this.deviceStatus?.status === "denied") {
      return html`
        <div class="device-flow">
          <p class="field-hint error" role="alert">${this.deviceStatus.message ?? "GitHub authorization did not complete."}</p>
          <button type="button" @click=${this.startDeviceLogin} ?disabled=${this.busy}>
            ${this.busy ? "Starting…" : "Get a new code"}
          </button>
        </div>
      `;
    }
    const validMinutes = Math.max(1, Math.ceil(this.deviceFlow.expires_in / 60));
    return html`
      <div class="device-flow">
        <div class="device-step">
          <p><strong>1. Copy this code</strong></p>
          <div class="device-code-row">
            <input
              class="device-code"
              aria-label="GitHub device code"
              readonly
              .value=${this.deviceFlow.user_code}
              @focus=${this.selectCode}
            />
            <button type="button" @click=${this.copyCode}>Copy code</button>
          </div>
          ${this.copyStatus ? html`<span class="field-hint" role="status" aria-live="polite">${this.copyStatus}</span>` : nothing}
        </div>
        <div class="device-step">
          <p><strong>2. Authorize Powercalc</strong></p>
          <a class="github-link" href=${this.deviceFlow.verification_uri} target="_blank" rel="noopener noreferrer">Continue on GitHub ↗</a>
          <span class="field-hint">Paste the code on GitHub. It is valid for up to ${validMinutes} minutes.</span>
        </div>
        <span class="field-hint" role="status" aria-live="polite">
          ${this.deviceStatus?.message ?? "Waiting for GitHub authorization… This page will connect automatically when you finish."}
        </span>
      </div>
    `;
  }

  private renderTokenFallback() {
    return html`
      <details class="github-card token-fallback">
        <summary>Use a personal access token instead</summary>
        <label>
          <span>Personal access token</span>
          <div class="token-row">
            <input name="github_token" type="password" autocomplete="off" placeholder="ghp_…" @keydown=${this.tokenKeydown} />
            <button type="button" @click=${this.saveToken} ?disabled=${this.busy}>Save token</button>
          </div>
          <small class="field-hint">Use only when device login is unavailable.</small>
        </label>
      </details>
    `;
  }

  private readonly startDeviceLogin = (): void => {
    this.copyStatus = "";
    emit(this, "github-device-start");
  };

  private readonly selectCode = (event: Event): void => {
    (event.currentTarget as HTMLInputElement).select();
  };

  private readonly copyCode = async (): Promise<void> => {
    const code = this.deviceFlow?.user_code;
    if (!code) return;
    if (await this.writeToClipboard(code)) {
      this.copyStatus = "Code copied.";
      return;
    }
    this.copyStatus = "Couldn’t copy automatically. Select the code and copy it manually.";
    this.querySelector<HTMLInputElement>(".device-code")?.select();
  };

  private async writeToClipboard(code: string): Promise<boolean> {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
        return true;
      }
    } catch {
      // Permission or focus problem, try the legacy path below.
    }
    return this.legacyCopy(code);
  }

  private legacyCopy(code: string): boolean {
    const scratch = document.createElement("textarea");
    scratch.value = code;
    scratch.setAttribute("readonly", "");
    scratch.style.cssText = "position:fixed;top:-1000px;opacity:0";
    document.body.append(scratch);
    try {
      scratch.select();
      scratch.setSelectionRange(0, code.length);
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      scratch.remove();
    }
  }

  private readonly saveToken = (): void => {
    const input = this.querySelector<HTMLInputElement>('input[name="github_token"]');
    const token = input?.value.trim() ?? "";
    if (!token) return;
    emit<string>(this, "github-token-save", token);
    if (input) input.value = "";
  };

  private readonly tokenKeydown = (event: KeyboardEvent): void => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    this.saveToken();
  };

  private readonly disconnect = (): void => {
    emit(this, "github-disconnect");
  };
}
