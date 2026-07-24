import { LitElement, css, html, nothing } from "lit";
import { createRef, ref } from "lit/directives/ref.js";
import type { AppSettings, Capabilities, ContributionAuthDeviceStatus, ContributionAuthState, ContributionDeviceFlow, EntityDescriptor, PowerMeterDiagnostic, SettingsSection, ShellyDiscoveryDevice } from "../types";
import { sharedStyles } from "../styles";
import "./power-meter-diagnostic";

export class SettingsView extends LitElement {
  static readonly properties = {
    powers: { attribute: false },
    settings: { attribute: false },
    capabilities: { attribute: false },
    busy: { type: Boolean },
    testing: { type: Boolean },
    testResult: { attribute: false },
    errorMessage: { type: String },
    meter: { state: true },
    activeSection: { state: true },
    initialSection: { attribute: false },
    contributionAuth: { attribute: false },
    contributionDeviceFlow: { attribute: false },
    contributionDeviceStatus: { attribute: false },
    contributionAuthBusy: { type: Boolean },
    contributionAuthError: { type: String },
    shellyDiscoveryDevices: { attribute: false },
    discoveringShellys: { type: Boolean },
    shellyDiscoveryError: { type: String },
    shellyDiscoveryAvailable: { attribute: false },
    shellyDiscoveryMessage: { attribute: false },
    shellyIp: { state: true },
  };

  powers: EntityDescriptor[] = [];
  settings?: AppSettings;
  capabilities?: Capabilities;
  meter?: AppSettings["power_meter"];
  busy = false;
  testing = false;
  testResult?: PowerMeterDiagnostic;
  errorMessage = "";
  activeSection: SettingsSection = "power_meter";
  initialSection?: SettingsSection;
  private appliedInitialSection = false;
  contributionAuth?: ContributionAuthState;
  contributionDeviceFlow?: ContributionDeviceFlow;
  contributionDeviceStatus?: ContributionAuthDeviceStatus;
  contributionAuthBusy = false;
  contributionAuthError = "";
  shellyDiscoveryDevices: ShellyDiscoveryDevice[] = [];
  discoveringShellys = false;
  shellyDiscoveryError = "";
  shellyDiscoveryAvailable?: boolean;
  shellyDiscoveryMessage?: string | null;
  private shellyIp?: string;
  private readonly form = createRef<HTMLFormElement>();

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-width: 0; max-width: 100%; }
    form { display: grid; gap: 1rem; min-width: 0; max-width: 100%; margin-top: 1rem; }
    .settings-layout { display: grid; grid-template-columns: minmax(180px, 0.32fr) minmax(0, 1fr); gap: 1.25rem; align-items: start; }
    .settings-nav { display: grid; gap: 0.4rem; padding: 0.45rem; border: 1px solid var(--line); border-radius: 12px; background: var(--field); }
    .settings-nav button { display: grid; grid-template-columns: 24px 1fr; align-items: center; gap: 0.65rem; min-height: 48px; padding: 0.65rem 0.75rem; border-color: transparent; background: transparent; text-align: left; }
    .settings-nav button:hover { border-color: var(--line); }
    .settings-nav button.active { border-color: var(--signal); background: color-mix(in srgb, var(--signal) 13%, transparent); color: var(--signal-strong); }
    .nav-icon { display: grid; place-items: center; width: 24px; height: 24px; }
    .nav-icon svg { width: 20px; height: 20px; }
    .settings-section { min-width: 0; padding: 1rem 1.1rem 1.2rem; border: 1px solid var(--line); border-radius: 12px; }
    .settings-section h3 { margin: 0 0 0.35rem; color: var(--ink); font-size: 1rem; }
    .settings-section > .muted { margin: 0 0 1rem; }
    .section-fields { display: grid; gap: 1rem; }
    label, fieldset { display: grid; gap: 0.4rem; min-width: 0; }
    label > span, legend { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    input, select {
      width: 100%; min-width: 0; max-width: 100%; min-height: 44px; border: 1px solid var(--line); border-radius: 9px;
      padding: 0.65rem 0.75rem; background: var(--field); color: var(--ink);
    }
    fieldset { border: 0; padding: 0; margin: 0; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
    .check { display: flex; grid-template-columns: none; align-items: flex-start; gap: 0.6rem; }
    .check input { width: auto; min-height: auto; margin-top: 0.2rem; accent-color: var(--signal); }
    .developer-option { margin-bottom: 1rem; padding: 0.85rem; border: 1px solid var(--signal); border-radius: 10px; background: color-mix(in srgb, var(--signal) 8%, transparent); }
    .developer-option strong { color: var(--ink); }
    .field-hint { color: var(--muted); font-size: 0.74rem; line-height: 1.4; }
    .context { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
    .quality-requirements { margin: -0.15rem 0 0; padding: 0.7rem 0.8rem; border-left: 3px solid var(--signal); background: color-mix(in srgb, var(--signal) 8%, transparent); color: var(--muted); font-size: 0.76rem; line-height: 1.45; }
    .test-row { display: grid; gap: 0.75rem; }
    .test-row > button { justify-self: start; }
    .test-row button { min-height: 40px; }
    .discovery { display: grid; gap: 0.65rem; padding: 0.8rem; border: 1px solid var(--line); border-radius: 10px; background: color-mix(in srgb, var(--field) 68%, transparent); }
    .discovery-header { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; }
    .discovery-header strong { color: var(--ink); font-size: 0.82rem; }
    .discovery-header button { min-height: 36px; padding: 0.45rem 0.7rem; }
    .discovery-status { margin: 0; color: var(--muted); font-size: 0.76rem; line-height: 1.45; }
    .discovery-status.error { color: var(--danger); }
    .github-card { display: grid; gap: 0.8rem; padding: 0.85rem; border: 1px solid var(--line); border-radius: 10px; background: color-mix(in srgb, var(--field) 70%, transparent); }
    .identity { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
    .identity strong, .code { color: var(--ink); }
    .code { font: 700 1.2rem/1 ui-monospace, monospace; letter-spacing: 0.12em; }
    .github-actions { display: flex; flex-wrap: wrap; gap: 0.65rem; align-items: center; }
    .github-actions a { color: var(--signal-strong); font-weight: 700; }
    .token-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.65rem; align-items: end; }
    @media (max-width: 700px) {
      .settings-layout { grid-template-columns: 1fr; }
      .settings-nav { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 520px) {
      .grid, .token-row { grid-template-columns: 1fr; }
      .settings-nav { grid-template-columns: 1fr; }
    }
  `];

  willUpdate() {
    // Honour a requested section (e.g. opened from the GitHub contribution shortcut) once,
    // while still letting the user switch sections afterwards.
    if (!this.appliedInitialSection && this.initialSection) {
      this.activeSection = this.initialSection;
      this.appliedInitialSection = true;
    }
  }

  render() {
    const selected = this.settings?.default_power_entity_id ?? "";
    const powerMeter = this.meter ?? this.settings?.power_meter ?? "hass";
    const defaults = this.settings?.measurement_defaults
      ?? this.capabilities?.defaults
      ?? { sleep_time: 2, sample_count: 1, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 };
    return html`
      <section class="panel" aria-labelledby="settings-title">
        <div class="context">
          <div>
            <p class="eyebrow">Settings</p>
            <h2 id="settings-title">Measurement defaults</h2>
          </div>
        </div>
        <p class="muted">Configure the measurement hardware once and set reusable defaults for new sessions.</p>
        <form ${ref(this.form)} @submit=${this.submit}>
          <div class="settings-layout">
            <nav class="settings-nav" aria-label="Settings sections">
              <button type="button" class=${this.activeSection === "power_meter" ? "active" : ""} aria-current=${this.activeSection === "power_meter" ? "page" : nothing} @click=${() => this.selectSection("power_meter")}>
                <span class="nav-icon" aria-hidden="true">${this.powerMeterIcon()}</span>
                <span>Power meter</span>
              </button>
              <button type="button" class=${this.activeSection === "measure_tuning" ? "active" : ""} aria-current=${this.activeSection === "measure_tuning" ? "page" : nothing} @click=${() => this.selectSection("measure_tuning")}>
                <span class="nav-icon" aria-hidden="true">${this.tuningIcon()}</span>
                <span>Measure tuning</span>
              </button>
              <button type="button" class=${this.activeSection === "github" ? "active" : ""} aria-current=${this.activeSection === "github" ? "page" : nothing} @click=${() => this.selectSection("github")}>
                <span class="nav-icon" aria-hidden="true">${this.githubIcon()}</span>
                <span>GitHub</span>
              </button>
            </nav>

            <section class="settings-section" ?hidden=${this.activeSection !== "power_meter"} aria-labelledby="power-meter-title">
              <h3 id="power-meter-title">Power meter</h3>
              <p class="muted">Choose where readings come from and set the default measurement hardware.</p>
              <div class="section-fields">
                <label>
                  <span>Measurement device name</span>
                  <input name="default_measure_device" .value=${this.settings?.default_measure_device ?? ""} required autocomplete="off" placeholder="e.g. Shelly Plug S" />
                </label>
                <label>
                  <span>Type</span>
                  <select name="power_meter" @change=${this.powerMeterChanged}>
                    <option value="hass" ?selected=${powerMeter === "hass"}>Home Assistant sensor</option>
                    <option value="shelly" ?selected=${powerMeter === "shelly"}>Shelly plug</option>
                    <option value="dummy" ?selected=${powerMeter === "dummy"}>Synthetic test meter</option>
                  </select>
                </label>
                ${powerMeter === "shelly" ? this.renderShellyFields() : nothing}
                ${powerMeter === "hass" ? html`<label>
                  <span>Power sensor</span>
                  <select name="default_power_entity_id" required @change=${this.powerMeterSettingsChanged}>
                    <option value="">Select a power sensor</option>
                    ${this.powers.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
                  </select>
                </label>` : nothing}
                ${powerMeter === "hass" ? html`<p class="quality-requirements">For reliable profiles, use a sensor with at least 0.1 W reported resolution and updates every 5 seconds or faster. Updates within 2 seconds are recommended.</p>` : nothing}
                ${powerMeter === "shelly" ? html`<p class="quality-requirements">Powercalc polls this device directly, so Home Assistant sensor resolution and update-frequency checks do not apply.</p>` : nothing}
                ${powerMeter === "dummy" ? nothing : this.renderTestRow()}
              </div>
            </section>

            <section class="settings-section" ?hidden=${this.activeSection !== "measure_tuning"} aria-labelledby="measure-tuning-title">
              <h3 id="measure-tuning-title">Measure tuning</h3>
              <p class="muted">Set reusable timing, sampling, and recovery defaults. Relevant values can still be adjusted per measurement.</p>
              ${this.capabilities?.developer_mode ? html`
                <div class="developer-option">
                  <label class="check">
                    <input type="checkbox" name="fast_test_mode" .checked=${this.settings?.fast_test_mode ?? false} />
                    <span>
                      <strong>Fast test mode</strong><br />
                      Synthetic light, fan, and charging workflows only. Skips waits and reduces measurement points so the output is not valid for contribution or real use.
                    </span>
                  </label>
                </div>
              ` : nothing}
              <div class="grid">
                ${this.numberField("sleep_time", "Settle time (seconds)", defaults.sleep_time, 0, 120, "0.1", "Wait after changing a device and between readings.")}
                ${this.numberField("sample_count", "Samples per point", defaults.sample_count, 1, 100, "1", "More samples reduce noise but increase measurement time.")}
                ${this.numberField("sleep_time_sample", "Time between samples (seconds)", defaults.sleep_time_sample, 0, 120, "1", "Used when taking more than one sample per point.")}
                ${this.numberField("max_retries", "Power meter retries", defaults.max_retries, 0, 100, "1", "Consecutive reading errors allowed before aborting.")}
                ${this.numberField("max_nudges", "Stale-reading nudges", defaults.max_nudges, 0, 20, "1", "Temporarily changes a light when its power sensor stops updating. Keep at 0 unless needed.")}
              </div>
            </section>

            <section class="settings-section" ?hidden=${this.activeSection !== "github"} aria-labelledby="github-title">
              <h3 id="github-title">GitHub</h3>
              <p class="muted">Connect GitHub once to open profile-library pull requests from completed measurements.</p>
              ${this.renderGithubSection()}
            </section>
          </div>
          ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
          <div class="actions">
            <button type="button" @click=${() => this.emit("back")}>Back</button>
            <button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Saving…" : "Save settings"}</button>
          </div>
        </form>
      </section>
    `;
  }

  private renderTestRow() {
    return html`
      <div class="test-row">
        <button type="button" @click=${this.test} ?disabled=${this.testing || this.busy}>${this.testing ? "Validating…" : "Validate measurement device"}</button>
        ${this.renderTestResult()}
      </div>`;
  }

  private renderTestResult() {
    if (!this.testResult) return nothing;
    return html`<measure-power-meter-diagnostic .diagnostic=${this.testResult}></measure-power-meter-diagnostic>`;
  }

  private renderGithubSection() {
    const identity = this.contributionAuth?.identity;
    return html`
      <div class="section-fields">
        <div class="github-card">
          ${this.contributionAuth?.connected ? html`
            <div class="identity">
              <div>
                <span class="field-hint">Connected as</span>
                <strong>${identity ? (identity.name ? `${identity.name} · ${identity.login}` : identity.login) : "GitHub"}</strong>
                ${this.contributionAuth.permissions_verified === false
                  ? html`<span class="field-hint">Identity verified. Fine-grained token permissions can only be confirmed during submission.</span>`
                  : nothing}
              </div>
              <button class="danger" type="button" @click=${this.disconnectGithub} ?disabled=${this.contributionAuthBusy}>Disconnect</button>
            </div>
          ` : html`
            <p class="muted">Use device login for the least typing. If device login is unavailable, paste a GitHub token with repository contribution access.</p>
            <div class="github-actions">
              <button
                type="button"
                @click=${this.startGithubDeviceLogin}
                ?disabled=${this.contributionAuthBusy || this.contributionAuth?.device_flow_available === false}
              >
                ${this.contributionAuthBusy ? "Starting…" : "Start device login"}
              </button>
              ${this.renderDeviceFlow()}
            </div>
            ${this.contributionAuth?.device_flow_available === false
              ? html`<p class="field-hint">Device login is not configured for this app build. Use a personal access token.</p>`
              : nothing}
          `}
        </div>
        ${this.contributionAuth?.connected ? nothing : this.renderTokenFallback()}
        <p class="notice">GitHub credentials are stored by the measure app and can be included in Home Assistant backups. Disconnect GitHub before sharing or exporting backups you do not control.</p>
        ${this.contributionAuthError ? html`<p class="notice error" role="alert">${this.contributionAuthError}</p>` : nothing}
      </div>
    `;
  }

  private renderDeviceFlow() {
    if (!this.contributionDeviceFlow) return nothing;
    const status = this.contributionDeviceStatus;
    return html`
      <span class="code" aria-label="GitHub device code">${this.contributionDeviceFlow.user_code}</span>
      <a href=${this.contributionDeviceFlow.verification_uri_complete ?? this.contributionDeviceFlow.verification_uri} target="_blank" rel="noopener noreferrer">Open GitHub</a>
      <button type="button" @click=${this.checkGithubDeviceLogin} ?disabled=${this.contributionAuthBusy}>Check login</button>
      ${status?.status === "pending" ? html`<span class="field-hint" role="status">${status.message ?? "Waiting for GitHub authorization."}</span>` : nothing}
      ${status?.status === "expired" || status?.status === "denied" ? html`<span class="field-hint error" role="alert">${status.message ?? "GitHub authorization did not complete."}</span>` : nothing}
    `;
  }

  private renderTokenFallback() {
    return html`
      <div class="github-card">
        <label>
          <span>Personal access token fallback</span>
          <div class="token-row">
            <input name="github_token" type="password" autocomplete="off" placeholder="ghp_…" @keydown=${this.tokenKeydown} />
            <button type="button" @click=${this.saveGithubToken} ?disabled=${this.contributionAuthBusy}>Save token</button>
          </div>
          <small class="field-hint">Use only when device login is unavailable.</small>
        </label>
      </div>
    `;
  }

  private renderShellyFields() {
    const address = this.shellyIp ?? this.settings?.shelly_ip ?? "";
    return html`
      <div class="discovery">
        <div class="discovery-header">
          <strong>Discovered Shelly devices</strong>
          <button type="button" @click=${this.discoverShellys} ?disabled=${this.discoveringShellys || this.busy}>
            ${this.discoveringShellys ? "Searching…" : "Refresh"}
          </button>
        </div>
        ${this.renderShellyDiscovery(address)}
      </div>
      <label>
        <span>Shelly IP address</span>
        <input name="shelly_ip" .value=${address} required autocomplete="off" placeholder="192.168.1.50" @input=${this.shellyIpChanged} />
        <small class="field-hint">Select a discovered device above or enter its IP address manually.</small>
      </label>`;
  }

  private renderShellyDiscovery(selectedAddress: string) {
    if (this.discoveringShellys) return html`<p class="discovery-status" role="status">Searching for Shelly devices on your network…</p>`;
    if (this.shellyDiscoveryError) return html`<p class="discovery-status error" role="alert">${this.shellyDiscoveryError}</p>`;
    if (this.shellyDiscoveryAvailable === false) {
      return html`<p class="discovery-status">${this.shellyDiscoveryMessage ?? "Shelly discovery is unavailable. Enter the IP address manually."}</p>`;
    }
    if (!this.shellyDiscoveryDevices.length) return html`<p class="discovery-status">No Shelly devices found. You can refresh or enter an IP address manually.</p>`;
    return html`<label>
      <span>Select device</span>
      <select name="discovered_shelly" @change=${this.discoveredShellyChanged}>
        <option value="">Select a discovered Shelly</option>
        ${this.shellyDiscoveryDevices.map((device) => html`
          <option
            value=${device.ip_address}
            ?selected=${device.supported && device.ip_address === selectedAddress}
            ?disabled=${!device.supported}
          >${this.shellyDeviceLabel(device)}</option>`)}
      </select>
    </label>`;
  }

  private shellyDeviceLabel(device: ShellyDiscoveryDevice): string {
    const identity = [device.name, device.model, device.generation === null ? null : `Gen ${device.generation}`, device.ip_address]
      .filter((part): part is string => Boolean(part))
      .join(" · ");
    return device.supported ? identity : `${identity} — ${device.reason ?? "Not supported"}`;
  }

  private collect(): AppSettings | null {
    const element = this.form.value;
    if (!element) return null;
    const data = new FormData(element);
    const value = data.get("default_power_entity_id");
    const powerMeterValue = data.get("power_meter");
    const powerMeter = (typeof powerMeterValue === "string" ? powerMeterValue : "hass") as AppSettings["power_meter"];
    const shellyIp = data.get("shelly_ip");
    const measureDevice = data.get("default_measure_device");
    return {
      default_power_entity_id: typeof value === "string" && value ? value : null,
      default_measure_device: typeof measureDevice === "string" && measureDevice.trim() ? measureDevice.trim() : null,
      power_meter: powerMeter,
      shelly_ip: powerMeter === "shelly" && typeof shellyIp === "string" ? shellyIp.trim() || null : null,
      fast_test_mode: data.get("fast_test_mode") === "on",
      measurement_defaults: {
        sleep_time: this.number(data, "sleep_time"),
        sample_count: this.number(data, "sample_count"),
        sleep_time_sample: this.number(data, "sleep_time_sample"),
        max_retries: this.number(data, "max_retries"),
        max_nudges: this.number(data, "max_nudges"),
      },
    };
  }

  private numberField(name: string, label: string, value: number, fallbackMin: number, fallbackMax: number, step: string, hint: string) {
    const { min, max } = this.capabilities?.limits?.[name] ?? { min: fallbackMin, max: fallbackMax };
    return html`<label>
      <span>${label}</span>
      <input type="number" name=${name} .value=${String(value)} min=${min} max=${max} step=${step} required />
      <small class="field-hint">${hint}</small>
    </label>`;
  }

  private number(data: FormData, name: string): number {
    return Number(data.get(name));
  }

  private submit(event: SubmitEvent): void {
    event.preventDefault();
    const settings = this.collect();
    if (!settings) return;
    this.dispatchEvent(new CustomEvent<AppSettings>("save", { detail: settings, bubbles: true, composed: true }));
  }

  private test(): void {
    const settings = this.collect();
    if (!settings) return;
    this.testResult = undefined;
    this.dispatchEvent(new CustomEvent<AppSettings>("test", { detail: settings, bubbles: true, composed: true }));
  }

  private powerMeterChanged(event: Event): void {
    this.clearTestResult();
    // Keep the choice in local state so an app-shell re-render can't clobber the
    // in-progress form (which would reset the meter type and typed Shelly IP).
    this.meter = (event.currentTarget as HTMLSelectElement).value as AppSettings["power_meter"];
    if (this.meter === "shelly") this.discoverShellys();
  }

  private powerMeterSettingsChanged(): void {
    this.clearTestResult();
  }

  private shellyIpChanged(event: Event): void {
    this.shellyIp = (event.currentTarget as HTMLInputElement).value;
    this.powerMeterSettingsChanged();
  }

  private discoveredShellyChanged(event: Event): void {
    const address = (event.currentTarget as HTMLSelectElement).value;
    if (!address) return;
    this.shellyIp = address;
    this.powerMeterSettingsChanged();
  }

  private discoverShellys(): void {
    this.dispatchEvent(new CustomEvent("shelly-discover", { bubbles: true, composed: true }));
  }

  private clearTestResult(): void {
    this.testResult = undefined;
    this.dispatchEvent(new CustomEvent("test-clear", { bubbles: true, composed: true }));
  }

  private startGithubDeviceLogin(): void {
    this.dispatchEvent(new CustomEvent("github-device-start", { bubbles: true, composed: true }));
  }

  private checkGithubDeviceLogin(): void {
    this.dispatchEvent(new CustomEvent("github-device-check", { bubbles: true, composed: true }));
  }

  private saveGithubToken(): void {
    const input = this.shadowRoot?.querySelector<HTMLInputElement>('input[name="github_token"]');
    const token = input?.value.trim() ?? "";
    if (!token) return;
    this.dispatchEvent(new CustomEvent<string>("github-token-save", { detail: token, bubbles: true, composed: true }));
    if (input) input.value = "";
  }

  private tokenKeydown(event: KeyboardEvent): void {
    if (event.key !== "Enter") return;
    event.preventDefault();
    this.saveGithubToken();
  }

  private disconnectGithub(): void {
    this.dispatchEvent(new CustomEvent("github-disconnect", { bubbles: true, composed: true }));
  }

  private selectSection(section: SettingsSection): void {
    this.activeSection = section;
  }

  private powerMeterIcon() {
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M13 2 5.5 13h6L11 22l7.5-11h-6L13 2Z"></path>
    </svg>`;
  }

  private tuningIcon() {
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10"></path>
      <circle cx="16" cy="7" r="2"></circle>
      <circle cx="8" cy="17" r="2"></circle>
    </svg>`;
  }

  private githubIcon() {
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9 19c-4.2 1.2-4.2-2-6-2.4M15 22v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.7 4.7 0 0 0-1.3-3.3 4.4 4.4 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.8 11.8 0 0 0-6.2 0C6.6 3.7 5.6 4 5.6 4a4.4 4.4 0 0 0-.1 3.2A4.7 4.7 0 0 0 4.2 10.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V22"></path>
    </svg>`;
  }

  private emit(name: "back"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-settings-view", SettingsView);
