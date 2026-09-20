import { html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { ProfileFormSection } from "./form-section";
import type { StandbyCalibrationActions, MeasurementRequest, StandbyEstimate } from "../../types";
import { emit } from "../../utils/events";
import { profileDeviceType } from "./device-specification-fields";
import "../shared/combobox";
import "./standby-setup";

@customElement("measure-profile-measurement-fields")
export class ProfileMeasurementFields extends ProfileFormSection {
  @property({ attribute: false }) measureDevices: string[] = [];
  @property({ type: Boolean }) measureDevicesLoading = false;
  @property({ type: String }) measureDevicesError = "";
  @property({ attribute: false }) standbyEstimate?: StandbyEstimate;
  @property({ type: Boolean }) standbyEstimateStale = false;
  @property({ attribute: false }) measurementRequest?: MeasurementRequest;
  @property({ type: Boolean }) standbyBusy = false;
  @property({ type: String }) standbyMessage = "";
  @property({ type: String }) sessionId = "";
  @property({ attribute: false }) calibrationActions?: StandbyCalibrationActions;
  @state() private confirmingStandby = false;

  render() {
    const measureDevice = this.fieldValue("measure_device", this.draft.measure_device);
    const hint = this.measureDevicesLoading
      ? "Loading names used by existing Powercalc profiles…"
      : "Choose an existing power meter or enter its manufacturer and model.";
    return html`<fieldset class="metadata-group" ?disabled=${this.busy || this.standbyBusy}>
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
        ${this.renderStandby()}
        ${this.renderTextarea(
          "measure_description",
          "Measurement description",
          this.draft.measure_description,
          "Add any relevant details about your measurement setup, device settings, or test conditions.",
        )}
      </div>
    </fieldset>`;
  }

  private renderStandby() {
    const isLight = profileDeviceType(this.draft) === "light";
    const value = this.fieldValue("standby_power", this.draft.standby_power);
    const estimated = this.fieldValue("standby_power_estimated", this.draft.standby_power_estimated ?? false) === "true";
    const error = this.fieldError("standby_power");
    const estimate = isLight ? this.standbyEstimate : undefined;
    const request = this.measurementRequest;
    const canMeasure = Boolean(request && !["manual", "ocr"].includes(request.power_meter.type));
    const measureTitle = canMeasure
      ? "Review the setup and measure standby"
      : "Requires an app-supported power meter";
    const measureLabel = this.standbyBusy ? "Measuring standby…" : "Measure standby";
    return html`
      ${this.renderStandbyCorrection(isLight, value)}
      <div class="field-stack standby-field">
        ${this.renderStandbyLabel(isLight)}
        <div class="standby-controls">
          <input id="standby-power" name="standby_power" type="number" min="0.05" step="any" ?required=${isLight}
            .value=${value} aria-invalid=${error ? "true" : "false"}
            aria-describedby=${error ? "standby_power-error standby-hint" : "standby-hint"} />
          <label class="standby-checkbox"><input name="standby_power_estimated" type="checkbox" .checked=${estimated} /> Estimated</label>
          <button type="button" ?disabled=${!canMeasure || this.standbyBusy}
            title=${measureTitle} @click=${() => { this.confirmingStandby = true; }}>${measureLabel}</button>
          ${this.renderStandbyEstimateButton(estimate)}
        </div>
        ${this.renderFieldError("standby_power")}
        ${isLight && estimated && this.standbyEstimateStale
          ? html`<p class="notice warning" role="alert">Connectivity or manufacturer changed after applying the standby estimate. Your standby value has not been updated. Click “Use estimated standby” again to apply the current suggestion, or enter a value manually. Submitting does not recalculate it.</p>`
          : nothing}
        ${this.renderStandbyConfirmation(request, canMeasure)}
        ${this.renderStandbyStatus()}
        ${this.renderStandbyHint(isLight)}
        ${this.renderStandbyEstimateStatus(isLight, estimate)}
      </div>
    `;
  }

  private renderStandbyCorrection(isLight: boolean, value: string) {
    const missing = isLight && !value;
    const invalid = Boolean(value) && Number(value) < 0.05;
    if (!missing && !invalid) return nothing;
    return html`<p class="notice warning">Standby power needs a correction before submitting. Your measurements are saved. Enter a separately measured value or use an estimate.</p>`;
  }

  private renderStandbyLabel(isLight: boolean) {
    const unit = isLight ? "W per light" : "W";
    const required = isLight ? html`<span class="required-marker" aria-hidden="true">*</span>` : nothing;
    return html`<label for="standby-power">Standby power (${unit}) ${required}</label>`;
  }

  private renderStandbyEstimateButton(estimate?: StandbyEstimate) {
    if (!estimate) return nothing;
    return html`<button type="button" @click=${() => emit(this, "standby-estimate-apply", estimate.power_w)}>Use estimated standby: ${estimate.power_w} W</button>`;
  }

  private renderStandbyConfirmation(request: MeasurementRequest | undefined, canMeasure: boolean) {
    if (!this.confirmingStandby || !canMeasure || !request) return nothing;
    if (request.measure_type === "light") return html`<measure-standby-setup
      .request=${request} .calibrationActions=${this.calibrationActions} .sessionId=${this.sessionId}
      .measuring=${this.standbyBusy} .measurementMessage=${this.standbyMessage}
      @standby-close=${() => { this.confirmingStandby = false; }}></measure-standby-setup>`;
    const controlled = ["light", "speaker", "fan"].includes(request.measure_type);
    const simulated = request.power_meter.type === "dummy" || request.controller?.type === "dummy";
    const simulatedNotice = simulated
      ? html`<p>This session uses dummy hardware. Results are simulated for testing; do not submit them as real measurements.</p>`
      : nothing;
    const instructions = controlled
      ? "This will turn off this session's device(s), wait for standby, and read the original power meter. The devices are left off."
      : "Put the device into its intended standby state first (not actively charging or running). This reads the original power meter without controlling the device.";
    const dummyLoadNotice = request.dummy_load
      ? "Keep the same warmed-up dummy load and wiring in place; the session calibration will be reused."
      : nothing;
    return html`<div class="notice warning" role="group" aria-label="Confirm standby measurement">
      ${simulatedNotice}
      <p>${instructions} No other measurements will be rerun.</p>
      <p>Confirm the same devices and meter are connected, with no other changing loads. ${dummyLoadNotice}</p>
      <div class="actions">
        <button type="button" @click=${() => { this.confirmingStandby = false; emit(this, "standby-measure"); }}>Confirm and measure standby</button>
        <button type="button" @click=${() => { this.confirmingStandby = false; }}>Cancel</button>
      </div>
    </div>`;
  }

  private renderStandbyStatus() {
    if (this.confirmingStandby || (!this.standbyBusy && !this.standbyMessage)) return nothing;
    const message = this.standbyBusy
      ? "Waiting for fresh standby readings. This may take a little while."
      : this.standbyMessage;
    return html`<small class="field-hint" role="status">${message}</small>`;
  }

  private renderStandbyHint(isLight: boolean) {
    const hint = isLight
      ? "Enter watts for one light, even when measuring several together."
      : "Optional: enter standby watts for this device. Leave blank to keep the existing profile value or template.";
    return html`<small id="standby-hint" class="field-hint">${hint}
      <a href="https://docs.powercalc.nl/contributing/measure/low-power-measurements/" target="_blank" rel="noopener noreferrer">Low-power measurement guide</a>
    </small>`;
  }

  private renderStandbyEstimateStatus(isLight: boolean, estimate?: StandbyEstimate) {
    if (!isLight) return nothing;
    return html`<small class="field-hint" role="status">${this.standbyEstimateHint(estimate)}</small>`;
  }

  private standbyEstimateHint(estimate?: StandbyEstimate): string {
    if (!estimate) return "Loading standby suggestion…";
    if (estimate.basis === "fallback") {
      return "Documented fallback; there are not enough comparable profiles or library suggestions are unavailable.";
    }
    const scope = estimate.basis === "manufacturer" ? " and manufacturer" : " across manufacturers";
    return `Median of ${estimate.profile_count} measured light profiles with the same connectivity${scope}.`;
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
