import { LitElement, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AppSettings, EntityDescriptor, PowerMeterDiagnostic, PowerMeterType, ShellyDiscoveryDevice } from "../../types";
import { DEFAULT_SHELLY_USERNAME, POWER_METER_LIST, meterFor } from "../../power-meter/registry";
import { emit } from "../../utils/events";
import type { ComboboxOption } from "../shared/combobox";
import "../shared/combobox";
import { optionSelect } from "../shared/fields";
import "../shared/power-meter-diagnostic";

@customElement("measure-settings-power-meter-section")
export class SettingsPowerMeterSection extends LitElement {
  @property({ attribute: false }) powers: EntityDescriptor[] = [];
  @property({ attribute: false }) settings?: AppSettings;
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

  @state() private meter?: PowerMeterType;
  @state() private measureDeviceValue = "";
  @state() private hassPowerEntity = "";
  @state() private shellyIp?: string;
  @state() private shellyUsername?: string;
  @state() private shellyPassword = "";
  @state() private clearShellyPassword = false;
  @state() private kasaIp?: string;

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  willUpdate(changedProperties: PropertyValues<this>): void {
    if (changedProperties.has("settings")) {
      this.measureDeviceValue = this.settings?.default_measure_device ?? "";
      this.hassPowerEntity = this.settings?.default_power_entity_id ?? "";
    }
  }

  render() {
    const powerMeter = this.meter ?? this.settings?.power_meter ?? "hass";
    const descriptor = meterFor(powerMeter);
    return html`
      <div class="section-fields">
        <measure-combobox
          name="default_measure_device"
          label="Power measurement device"
          .value=${this.measureDeviceValue}
          .options=${this.measureDeviceOptions()}
          placeholder="e.g. Shelly Plug S"
          .hint=${this.measureDevicesLoading
            ? "Loading names used by existing Powercalc profiles…"
            : "Manufacturer and model of the meter used to take readings. This is prefilled in each profile and can still be changed there."}
          required
          allowCustom
          @combobox-change=${this.measureDeviceChanged}
        >
          <input slot="value" type="hidden" name="default_measure_device" .value=${this.measureDeviceValue} />
        </measure-combobox>
        ${this.measureDevicesError
          ? html`<small class="field-hint error" role="status">Library suggestions are unavailable; manual entry still works.</small>`
          : nothing}
        <label>
          <span>Power measurement device firmware</span>
          <input
            name="default_measure_device_firmware"
            .value=${this.settings?.default_measure_device_firmware ?? ""}
            autocomplete="off"
            placeholder="Optional firmware version"
          />
          <small class="field-hint">Prefilled in new profile metadata and editable for each profile.</small>
        </label>
        ${optionSelect("power_meter", "Type", POWER_METER_LIST.map((meter) => ({ value: meter.type, label: meter.label })), {
          selected: powerMeter,
          required: true,
          placeholder: "Select a power meter type",
          onChange: this.powerMeterChanged,
        })}
        ${this.renderMeterFields(powerMeter)}
        ${descriptor.qualityNote ? html`<p class="quality-requirements">${descriptor.qualityNote}</p>` : nothing}
        ${descriptor.validatable ? this.renderTestRow() : nothing}
      </div>
    `;
  }

  private measureDeviceOptions(): ComboboxOption[] {
    if (this.measureDevicesLoading || this.measureDevicesError) return [];
    return this.measureDevices.map((device) => ({ value: device, label: device }));
  }

  private readonly measureDeviceChanged = (event: CustomEvent<{ value: string }>): void => {
    this.measureDeviceValue = event.detail.value;
  };

  private readonly hassPowerEntityChanged = (event: CustomEvent<{ value: string }>): void => {
    this.hassPowerEntity = event.detail.value;
    this.powerMeterSettingsChanged();
  };

  private renderMeterFields(type: PowerMeterType) {
    const fields: Record<PowerMeterType, () => unknown> = {
      hass: () => this.renderHassFields(),
      shelly: () => this.renderShellyFields(),
      kasa: () => this.renderKasaFields(),
      dummy: () => nothing,
    };
    return fields[type]();
  }

  private renderHassFields() {
    const options = this.powers.map((entity) => ({
      value: entity.entity_id,
      label: `${entity.name} · ${entity.entity_id}`,
    }));
    return html`
      <measure-combobox
        name="default_power_entity_id"
        label="Power sensor"
        .value=${this.hassPowerEntity}
        .options=${options}
        placeholder="Search power sensors"
        required
        @combobox-change=${this.hassPowerEntityChanged}
      >
        <input slot="value" type="hidden" name="default_power_entity_id" .value=${this.hassPowerEntity} />
      </measure-combobox>`;
  }

  private renderTestRow() {
    return html`
      <div class="test-row">
        <button type="button" @click=${this.test} ?disabled=${this.testing || this.busy}>${this.testing ? "Validating…" : "Validate measurement device"}</button>
        ${this.testResult ? html`<measure-power-meter-diagnostic .diagnostic=${this.testResult}></measure-power-meter-diagnostic>` : nothing}
      </div>`;
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
      </label>
      <div class="grid">
        <label>
          <span>Shelly username</span>
          <input name="shelly_username" .value=${this.shellyUsername ?? this.settings?.shelly_username ?? DEFAULT_SHELLY_USERNAME} required autocomplete="username" maxlength="50" @input=${this.shellyUsernameChanged} />
          <small class="field-hint">Gen1 devices may use a custom username. Gen2 and newer always use admin.</small>
        </label>
        <label>
          <span>Shelly password</span>
          <input name="shelly_password" type="password" .value=${this.shellyPassword} autocomplete="new-password" maxlength="255" placeholder=${this.settings?.shelly_password_configured ? "Saved password (leave blank to keep)" : "Optional"} @input=${this.shellyPasswordChanged} />
          <small class="field-hint">Stored privately in the app and never returned by the API.</small>
        </label>
      </div>
      ${this.renderClearShellyPassword()}`;
  }

  private renderClearShellyPassword() {
    if (!this.settings?.shelly_password_configured) return nothing;
    return html`
      <label class="check">
        <input name="clear_shelly_password" type="checkbox" .checked=${this.clearShellyPassword} @change=${this.clearShellyPasswordChanged} />
        <span>Remove the saved Shelly password</span>
      </label>`;
  }

  private renderShellyDiscovery(selectedAddress: string) {
    if (this.discoveringShellys) return html`<p class="discovery-status" role="status">Searching for Shelly devices on your network…</p>`;
    if (this.shellyDiscoveryError) return html`<p class="discovery-status error" role="alert">${this.shellyDiscoveryError}</p>`;
    if (this.shellyDiscoveryAvailable === false) {
      return html`<p class="discovery-status">${this.shellyDiscoveryMessage ?? "Shelly discovery is unavailable. Enter the IP address manually."}</p>`;
    }
    if (!this.shellyDiscoveryDevices.length) return html`<p class="discovery-status">No Shelly devices found. You can refresh or enter an IP address manually.</p>`;
    return optionSelect("discovered_shelly", "Select device", [
      { value: "", label: "Select a discovered Shelly" },
      ...this.shellyDiscoveryDevices.map((device) => ({
        value: device.ip_address,
        label: this.shellyDeviceLabel(device),
        disabled: !device.supported && !device.auth_required,
      })),
    ], {
      selected: selectedAddress,
      placeholder: "Search discovered Shelly devices",
      onChange: this.discoveredShellyChanged,
    });
  }

  private renderKasaFields() {
    const address = this.kasaIp ?? this.settings?.kasa_ip ?? "";
    return html`
      <label>
        <span>Kasa IP address</span>
        <input name="kasa_ip" .value=${address} required autocomplete="off" placeholder="192.168.1.50" @input=${this.kasaIpChanged} />
        <small class="field-hint">Enter the IP address of a Kasa plug with energy monitoring, such as a KP115 or HS110. Give it a static lease in your router so it stays reachable.</small>
      </label>`;
  }

  private shellyDeviceLabel(device: ShellyDiscoveryDevice): string {
    const identity = [device.name, device.model, device.generation === null ? null : `Gen ${device.generation}`, device.ip_address]
      .filter((part): part is string => Boolean(part))
      .join(" · ");
    return device.supported ? identity : `${identity} — ${device.reason ?? "Not supported"}`;
  }

  private readonly test = (): void => {
    emit(this, "power-meter-test");
  };

  private readonly powerMeterChanged = (event: Event): void => {
    this.clearTestResult();
    this.meter = (event.currentTarget as HTMLInputElement).value as PowerMeterType;
    if (meterFor(this.meter).discoverable) this.discoverShellys();
  };

  private powerMeterSettingsChanged(): void {
    this.clearTestResult();
  }

  private readonly shellyIpChanged = (event: Event): void => {
    this.shellyIp = (event.currentTarget as HTMLInputElement).value;
    this.powerMeterSettingsChanged();
  };

  private readonly shellyUsernameChanged = (event: Event): void => {
    this.shellyUsername = (event.currentTarget as HTMLInputElement).value;
    this.powerMeterSettingsChanged();
  };

  private readonly shellyPasswordChanged = (event: Event): void => {
    this.shellyPassword = (event.currentTarget as HTMLInputElement).value;
    this.clearShellyPassword = false;
    this.powerMeterSettingsChanged();
  };

  private readonly clearShellyPasswordChanged = (event: Event): void => {
    this.clearShellyPassword = (event.currentTarget as HTMLInputElement).checked;
    if (this.clearShellyPassword) this.shellyPassword = "";
    this.powerMeterSettingsChanged();
  };

  private readonly kasaIpChanged = (event: Event): void => {
    this.kasaIp = (event.currentTarget as HTMLInputElement).value;
    this.powerMeterSettingsChanged();
  };

  private readonly discoveredShellyChanged = (event: Event): void => {
    const address = (event.currentTarget as HTMLInputElement).value;
    if (!address) return;
    this.shellyIp = address;
    this.powerMeterSettingsChanged();
  };

  private discoverShellys(): void {
    emit(this, "shelly-discover");
  }

  private clearTestResult(): void {
    emit(this, "test-clear");
  }
}
