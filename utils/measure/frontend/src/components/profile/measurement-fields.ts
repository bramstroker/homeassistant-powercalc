import { html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { ProfileFormSection } from "./form-section";
import "../shared/combobox";

@customElement("measure-profile-measurement-fields")
export class ProfileMeasurementFields extends ProfileFormSection {
  @property({ attribute: false }) measureDevices: string[] = [];
  @property({ type: Boolean }) measureDevicesLoading = false;
  @property({ type: String }) measureDevicesError = "";

  render() {
    const measureDevice = this.fieldValue("measure_device", this.draft.measure_device);
    const hint = this.measureDevicesLoading
      ? "Loading names used by existing Powercalc profiles…"
      : "Choose an existing power meter or enter its manufacturer and model.";
    return html`<fieldset class="metadata-group" ?disabled=${this.busy}>
      <legend>Measurement</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">Document the equipment and method used to create the profile.</p>
        <div class="contribution-grid">
          <div class="field-stack">
            <measure-combobox
              name="measure_device"
              label="Measurement device"
              .value=${measureDevice}
              .options=${this.measureDevices.map((device) => ({ value: device, label: device }))}
              .error=${this.fieldError("measure_device")}
              ?disabled=${this.busy}
              placeholder="e.g. Shelly Plug S"
              .hint=${hint}
              required
              allowCustom
            >
              <input slot="value" type="hidden" name="measure_device" .value=${measureDevice} />
            </measure-combobox>
            ${this.measureDevicesError
              ? html`<small class="field-hint error" role="status">Library suggestions are unavailable; manual entry still works.</small>`
              : nothing}
          </div>
          ${this.renderInput("measure_device_firmware", "Device firmware", this.draft.measure_device_firmware ?? "", {
            required: false,
          })}
          ${this.renderMainsVoltage()}
        </div>
        ${this.renderTextarea("measure_description", "Measurement description", this.draft.measure_description)}
      </div>
    </fieldset>`;
  }

  private renderMainsVoltage() {
    if (this.draft.voltage_range) {
      return html`
        <label>
          <span>Nominal mains voltage</span>
          <input type="text" .value=${`${this.draft.mains_voltage ?? "—"} V`} readonly />
          <small class="field-hint">Calculated from the measured ${this.draft.voltage_range.min}–${this.draft.voltage_range.max} V range.</small>
        </label>`;
    }
    return html`
      <measure-combobox
        name="mains_voltage"
        label="Nominal mains voltage"
        .value=${this.fieldValue("mains_voltage", this.draft.mains_voltage)}
        .options=${[120, 230].map((voltage) => ({ value: String(voltage), label: `${voltage} V` }))}
        .error=${this.fieldError("mains_voltage")}
        ?disabled=${this.busy}
        placeholder="Select voltage"
        hint="The power meter did not report a voltage range, so select the nominal mains voltage used during measurement."
        required
      ></measure-combobox>`;
  }
}
