import { LitElement, css, html, nothing, svg, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { createRef, ref } from "lit/directives/ref.js";
import type { AppSettings, AppSettingsUpdate, Capabilities, ContributionAuthDeviceStatus, ContributionAuthState, ContributionDeviceFlow, EntityDescriptor, MeasureParameterName, PowerMeterDiagnostic, SettingsSection, ShellyDiscoveryDevice } from "../../types";
import { DEFAULT_SHELLY_USERNAME, settingsFromForm } from "../../power-meter";
import { formRaw, formText, formTextOrNull } from "../../form";
import { emit } from "../../events";
import { sharedStyles } from "../../styles";
import "./github-section";
import "./power-meter-section";

interface SettingsSectionDescriptor {
  id: SettingsSection;
  label: string;
  icon: () => unknown;
}

const icon = (path: unknown) => html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;

/** The sections of the settings screen, in the order the navigation lists them. */
const SETTINGS_SECTIONS: SettingsSectionDescriptor[] = [
  {
    id: "power_meter",
    label: "Power meter",
    icon: () => icon(svg`<path d="M13 2 5.5 13h6L11 22l7.5-11h-6L13 2Z"></path>`),
  },
  {
    id: "profile",
    label: "Profile metadata",
    icon: () => icon(svg`<path d="M4 4h16v16H4z"></path><path d="M8 9h8M8 13h8M8 17h5"></path>`),
  },
  {
    id: "measure_tuning",
    label: "Measure tuning",
    icon: () => icon(svg`
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10"></path>
      <circle cx="16" cy="7" r="2"></circle>
      <circle cx="8" cy="17" r="2"></circle>
    `),
  },
  {
    id: "github",
    label: "GitHub",
    icon: () => icon(svg`<path d="M9 19c-4.2 1.2-4.2-2-6-2.4M15 22v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.7 4.7 0 0 0-1.3-3.3 4.4 4.4 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.8 11.8 0 0 0-6.2 0C6.6 3.7 5.6 4 5.6 4a4.4 4.4 0 0 0-.1 3.2A4.7 4.7 0 0 0 4.2 10.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V22"></path>`),
  },
];

@customElement("measure-settings-view")
export class SettingsView extends LitElement {
  @property({ attribute: false })
  powers: EntityDescriptor[] = [];

  @property({ attribute: false })
  settings?: AppSettings;

  @property({ attribute: false })
  capabilities?: Capabilities;

  @property({ attribute: false })
  measureDevices: string[] = [];

  @property({ type: Boolean })
  measureDevicesLoading = false;

  @property({ type: String })
  measureDevicesError = "";

  @property({ type: Boolean })
  busy = false;

  @property({ type: Boolean })
  testing = false;

  @property({ attribute: false })
  testResult?: PowerMeterDiagnostic;

  @property({ type: String })
  errorMessage = "";

  @state()
  activeSection: SettingsSection = "power_meter";

  @property({ attribute: false })
  initialSection?: SettingsSection;

  private appliedInitialSection = false;

  @property({ attribute: false })
  contributionAuth?: ContributionAuthState;

  @property({ attribute: false })
  contributionDeviceFlow?: ContributionDeviceFlow;

  @property({ attribute: false })
  contributionDeviceStatus?: ContributionAuthDeviceStatus;

  @property({ type: Boolean })
  contributionAuthBusy = false;

  @property({ type: String })
  contributionAuthError = "";

  @state()
  private contributorGithubValue?: string;

  @property({ attribute: false })
  shellyDiscoveryDevices: ShellyDiscoveryDevice[] = [];

  @property({ type: Boolean })
  discoveringShellys = false;

  @property({ type: String })
  shellyDiscoveryError = "";

  @property({ attribute: false })
  shellyDiscoveryAvailable?: boolean;

  @property({ attribute: false })
  shellyDiscoveryMessage?: string | null;

  private readonly form = createRef<HTMLFormElement>();

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-width: 0; max-width: 100%; }
    measure-settings-github-section, measure-settings-power-meter-section { display: contents; }
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
    .check { align-items: flex-start; gap: 0.6rem; }
    .check input { margin-top: 0.2rem; }
    .developer-option { margin-bottom: 1rem; padding: 0.85rem; border: 1px solid var(--signal); border-radius: 10px; background: color-mix(in srgb, var(--signal) 8%, transparent); }
    .developer-option strong { color: var(--ink); }
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
    .github-card > button, .device-flow > button { justify-self: start; }
    .identity { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
    .identity strong, .device-code { color: var(--ink); }
    .device-flow { display: grid; gap: 0.85rem; }
    .device-step { display: grid; gap: 0.45rem; }
    .device-step p { margin: 0; }
    .device-code-row { display: grid; grid-template-columns: minmax(0, 220px) auto; gap: 0.65rem; align-items: center; }
    .device-code {
      width: 100%; min-height: 44px; padding: 0.65rem 0.75rem; border: 1px solid var(--line); border-radius: 9px;
      background: var(--canvas); font: 700 1.2rem/1 ui-monospace, monospace; letter-spacing: 0.12em; text-align: center;
    }
    .github-link {
      justify-self: start; min-height: 44px; padding: 0.65rem 0.85rem; border: 1px solid var(--signal); border-radius: 9px;
      display: inline-flex; align-items: center; background: var(--signal); color: var(--on-signal); font-weight: 750; text-decoration: none;
    }
    .github-link:hover { filter: brightness(1.08); }
    .token-fallback summary { cursor: pointer; color: var(--ink); font-weight: 700; }
    .token-fallback label { margin-top: 0.8rem; }
    .token-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.65rem; align-items: end; }
    @media (max-width: 700px) {
      .settings-layout { grid-template-columns: 1fr; }
      .settings-nav { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    }
    @media (max-width: 520px) {
      .token-row, .device-code-row { grid-template-columns: 1fr; }
      .settings-nav { grid-template-columns: 1fr; }
    }
  `];

  willUpdate(changedProperties: PropertyValues<this>) {
    if (changedProperties.has("settings")) {
      this.contributorGithubValue = undefined;
    }
    // Honour a requested section (e.g. opened from the GitHub contribution shortcut) once,
    // while still letting the user switch sections afterwards.
    if (!this.appliedInitialSection && this.initialSection) {
      this.activeSection = this.initialSection;
      this.appliedInitialSection = true;
    }
  }

  protected async getUpdateComplete(): Promise<boolean> {
    const complete = await super.getUpdateComplete();
    const sections = this.shadowRoot?.querySelectorAll<LitElement>(
      "measure-settings-github-section, measure-settings-power-meter-section",
    );
    await Promise.all([...sections ?? []].map((section) => section.updateComplete));
    return complete;
  }

  render() {
    const connectedGithubUsername = this.contributionAuth?.connected ? this.contributionAuth.identity?.login : "";
    const contributorGithub = this.contributorGithubValue
      ?? (this.settings?.default_contributor_github || connectedGithubUsername || "");
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
              ${SETTINGS_SECTIONS.map((section) => this.renderNavButton(section))}
            </nav>

            <section class="settings-section" ?hidden=${this.activeSection !== "power_meter"} aria-labelledby="power-meter-title">
              <h3 id="power-meter-title">Power meter</h3>
              <p class="muted">Choose where readings come from and set the hardware metadata added to new profiles.</p>
              <measure-settings-power-meter-section
                .powers=${this.powers}
                .settings=${this.settings}
                .measureDevices=${this.measureDevices}
                .measureDevicesLoading=${this.measureDevicesLoading}
                .measureDevicesError=${this.measureDevicesError}
                .busy=${this.busy}
                .testing=${this.testing}
                .testResult=${this.testResult}
                .shellyDiscoveryDevices=${this.shellyDiscoveryDevices}
                .discoveringShellys=${this.discoveringShellys}
                .shellyDiscoveryError=${this.shellyDiscoveryError}
                .shellyDiscoveryAvailable=${this.shellyDiscoveryAvailable}
                .shellyDiscoveryMessage=${this.shellyDiscoveryMessage}
                @power-meter-test=${this.test}
                @test-clear=${this.clearTestResult}
              ></measure-settings-power-meter-section>
            </section>

            <section class="settings-section" ?hidden=${this.activeSection !== "profile"} aria-labelledby="profile-metadata-title">
              <h3 id="profile-metadata-title">Profile metadata</h3>
              <p class="muted">Set contributor details once. They are prefilled when preparing every profile and remain editable there.</p>
              <div class="section-fields">
                <label>
                  <span>Contributor name</span>
                  <input name="default_contributor_name" .value=${this.settings?.default_contributor_name ?? ""} autocomplete="name" />
                </label>
                <label>
                  <span>GitHub username</span>
                  <input
                    name="default_contributor_github"
                    .value=${contributorGithub}
                    @input=${this.contributorGithubChanged}
                    autocomplete="username"
                  />
                </label>
                <label>
                  <span>Email (optional)</span>
                  <input name="default_contributor_email" type="email" .value=${this.settings?.default_contributor_email ?? ""} autocomplete="email" />
                </label>
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
              <measure-settings-github-section
                .auth=${this.contributionAuth}
                .deviceFlow=${this.contributionDeviceFlow}
                .deviceStatus=${this.contributionDeviceStatus}
                .busy=${this.contributionAuthBusy}
                .errorMessage=${this.contributionAuthError}
              ></measure-settings-github-section>
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

  private renderNavButton({ id, label, icon }: SettingsSectionDescriptor) {
    const active = this.activeSection === id;
    return html`
      <button type="button" class=${active ? "active" : ""} aria-current=${active ? "page" : nothing} @click=${() => this.selectSection(id)}>
        <span class="nav-icon" aria-hidden="true">${icon()}</span>
        <span>${label}</span>
      </button>
    `;
  }

  private contributorGithubChanged(event: Event): void {
    this.contributorGithubValue = (event.target as HTMLInputElement).value;
  }

  private collect(): AppSettingsUpdate | null {
    const element = this.form.value;
    if (!element) return null;
    const data = new FormData(element);
    const meter = settingsFromForm(data);
    // Credentials stay here rather than in the registry: they are only ever entered, never read back.
    const shellyPassword = formRaw(data, "shelly_password");
    return {
      ...meter,
      default_measure_device: formTextOrNull(data, "default_measure_device"),
      default_measure_device_firmware: formTextOrNull(data, "default_measure_device_firmware"),
      default_contributor_name: formTextOrNull(data, "default_contributor_name"),
      default_contributor_github: formTextOrNull(data, "default_contributor_github"),
      default_contributor_email: formTextOrNull(data, "default_contributor_email"),
      shelly_username: formText(data, "shelly_username") || DEFAULT_SHELLY_USERNAME,
      shelly_password_configured: this.settings?.shelly_password_configured ?? false,
      shelly_password: meter.power_meter === "shelly" ? shellyPassword || null : null,
      clear_shelly_password: data.get("clear_shelly_password") === "on",
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

  private numberField(name: MeasureParameterName, label: string, value: number, fallbackMin: number, fallbackMax: number, step: string, hint: string) {
    const { min, max } = this.capabilities?.limits?.[name] ?? { min: fallbackMin, max: fallbackMax };
    return html`<label>
      <span>${label}</span>
      <input type="number" name=${name} min=${min} max=${max} step=${step} .value=${String(value)} required />
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
    emit<AppSettingsUpdate>(this, "save", settings);
  }

  private test(): void {
    const settings = this.collect();
    if (!settings) return;
    this.testResult = undefined;
    emit<AppSettingsUpdate>(this, "test", settings);
  }

  private clearTestResult(): void {
    this.testResult = undefined;
  }

  private selectSection(section: SettingsSection): void {
    this.activeSection = section;
  }

  private emit(name: "back"): void {
    emit(this, name);
  }
}
