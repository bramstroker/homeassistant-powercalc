import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AppSettings, AppSettingsUpdate, EntityDescriptor, PowerMeterDiagnostic, SessionPowerMeter, ShellyDiscoveryDevice } from "../../types";
import { DEFAULT_SHELLY_USERNAME, settingsForSessionMeter, settingsFromForm, specFromSettings } from "../../power-meter/registry";
import { formText, formTextOrNull } from "../../utils/form";
import { emit } from "../../utils/events";
import { sharedStyles } from "../../styles";
import { powerMeterStyles } from "./power-meter-section";

@customElement("measure-session-power-meter-view")
export class SessionPowerMeterView extends LitElement {
  @property({ attribute: false }) configuration?: SessionPowerMeter;
  @property({ attribute: false }) settings?: AppSettings;
  @property({ attribute: false }) powers: EntityDescriptor[] = [];
  @property({ attribute: false }) voltages: EntityDescriptor[] = [];
  @property({ attribute: false }) measureDevices: string[] = [];
  @property({ type: Boolean }) measureDevicesLoading = false;
  @property({ type: String }) measureDevicesError = "";
  @property({ type: Boolean }) busy = false;
  @property({ type: Boolean }) testing = false;
  @property({ attribute: false }) testResult?: PowerMeterDiagnostic;
  @property({ attribute: false }) shellyDiscoveryDevices: ShellyDiscoveryDevice[] = [];
  @property({ type: Boolean }) discoveringShellys = false;
  @property({ type: String }) shellyDiscoveryError = "";
  @property({ attribute: false }) shellyDiscoveryAvailable?: boolean;
  @property({ attribute: false }) shellyDiscoveryMessage?: string | null;

  @state() private editorSettings?: AppSettings;

  static readonly styles = [sharedStyles, powerMeterStyles, css`
    :host { display: block; min-width: 0; }
    measure-settings-power-meter-section { display: contents; }
    form { display: grid; gap: 1rem; margin-top: 1rem; }
    .settings-section { max-width: 680px; min-width: 0; padding: 1rem 1.1rem 1.2rem; border: 1px solid var(--line); border-radius: 12px; }
  `];

  willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("configuration") && this.configuration && this.settings) {
      this.editorSettings = settingsForSessionMeter(this.settings, this.configuration);
    }
  }

  protected async getUpdateComplete(): Promise<boolean> {
    const complete = await super.getUpdateComplete();
    await this.shadowRoot?.querySelector<LitElement>("measure-settings-power-meter-section")?.updateComplete;
    return complete;
  }

  render() {
    if (!this.editorSettings) return nothing;
    const meter = this.configuration?.power_meter;
    return html`
      <section class="panel" aria-labelledby="session-meter-title">
        <p class="eyebrow">Current measurement</p>
        <h2 id="session-meter-title">Power meter for this measurement</h2>
        <p class="muted">Changes apply only to this draft. Defaults for future measurements stay unchanged.</p>
        <form @submit=${this.save}>
          <section class="settings-section">
            <measure-settings-power-meter-section
              sessionOnly .settings=${this.editorSettings} .powers=${this.powers} .voltages=${this.voltages}
              .initialVoltageEntityId=${meter?.type === "hass" ? meter.voltage_entity_id : null}
              .measureDevices=${this.measureDevices} .measureDevicesLoading=${this.measureDevicesLoading}
              .measureDevicesError=${this.measureDevicesError} .busy=${this.busy}
              .testing=${this.testing} .testResult=${this.testResult}
              .shellyDiscoveryDevices=${this.shellyDiscoveryDevices} .discoveringShellys=${this.discoveringShellys}
              .shellyDiscoveryError=${this.shellyDiscoveryError} .shellyDiscoveryAvailable=${this.shellyDiscoveryAvailable}
              .shellyDiscoveryMessage=${this.shellyDiscoveryMessage}
              @power-meter-test=${this.test}
            ></measure-settings-power-meter-section>
          </section>
          <div class="actions">
            <button type="button" @click=${() => emit(this, "back")} ?disabled=${this.busy}>Cancel</button>
            <button class="primary" type="submit" ?disabled=${this.busy}>Use for this measurement</button>
          </div>
        </form>
      </section>`;
  }

  private collect(): { configuration: SessionPowerMeter; settings: AppSettingsUpdate } | undefined {
    const form = this.shadowRoot?.querySelector("form");
    if (!form || !this.editorSettings) return;
    const data = new FormData(form);
    const settings: AppSettingsUpdate = {
      ...this.editorSettings,
      ...settingsFromForm(data),
      default_measure_device: formTextOrNull(data, "default_measure_device"),
      shelly_username: formText(data, "shelly_username") || DEFAULT_SHELLY_USERNAME,
    };
    let meter = specFromSettings(settings, { powers: this.powers, voltages: this.voltages });
    const previous = this.configuration?.power_meter;
    if (previous?.type === meter.type) meter = { ...previous, ...meter };
    if (meter.type === "hass") meter = { ...meter, voltage_entity_id: formTextOrNull(data, "voltage_entity_id") };
    return { configuration: { power_meter: meter, measure_device: settings.default_measure_device ?? "" }, settings };
  }

  private save(event: SubmitEvent): void {
    event.preventDefault();
    const value = this.collect();
    if (value) emit<SessionPowerMeter>(this, "save", value.configuration);
  }

  private test(): void {
    const value = this.collect();
    if (value) emit<AppSettingsUpdate>(this, "test", value.settings);
  }
}
