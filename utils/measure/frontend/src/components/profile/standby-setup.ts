import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { DummyLoadCalibration, LightMeasurementRequest, MeasurementParameters, CalibrationJob, StandbyCalibrationActions, PowerMeterSpec } from "../../types";
import { sharedStyles } from "../../styles";
import { emit } from "../../utils/events";

@customElement("measure-standby-setup")
export class StandbySetup extends LitElement {
  @property({ attribute: false }) request!: LightMeasurementRequest;
  @property({ type: String }) sessionId = "";
  @property({ attribute: false }) calibrationActions?: StandbyCalibrationActions;
  @state() private savedCalibration: DummyLoadCalibration | null = null;
  @state() private checkingCalibration = false;
  private calibrationJob?: CalibrationJob;
  private pollTimer?: ReturnType<typeof setTimeout>;
  private meterRevision = 0;
  @property({ type: Boolean }) measuring = false;
  @property({ type: String }) measurementMessage = "";
  @state() private elapsedSeconds = 0;
  @state() private measurementStarted = false;
  private expectedSeconds = 0;
  private startedAt = 0;
  private progressTimer?: ReturnType<typeof setInterval>;
  @state() private busy = false;
  @state() private message = "";
  @state() private loadMode = "original";
  static readonly styles = [sharedStyles, css`
    dialog { width: min(720px, calc(100% - 2rem)); max-height: calc(100dvh - 2rem); padding: 0; border: 1px solid var(--line); border-radius: 16px; background: var(--surface); color: var(--ink); box-shadow: 0 24px 80px rgb(0 0 0 / 0.45); }
    dialog[open] { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; }
    dialog::backdrop { background: rgb(0 0 0 / 0.65); }
    header, footer { padding: 1.25rem 1.5rem; }
    header { border-bottom: 1px solid var(--line); }
    h2 { margin: 0 0 0.4rem; font-size: 1.3rem; }
    h3 { margin: 0 0 0.8rem; font-size: 1rem; }
    p { margin: 0; line-height: 1.5; font-size: 0.88rem; color: var(--muted); }
    .body { overflow-y: auto; padding: 1.25rem 1.5rem; }
    fieldset { gap: 1.5rem; }
    .fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
    .wide { grid-column: 1 / -1; }
    .timing { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .calibration { display: grid; gap: 0.85rem; margin-top: 1rem; padding: 1rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); }
    .calibration button { justify-self: start; }
    .notice { margin-bottom: 1.25rem; }
    .instructions { display: grid; gap: 0.6rem; }
    fieldset[hidden] { display: none; }
    .progress-panel { display: grid; gap: 0.8rem; padding: 1.25rem; border: 1px solid var(--line); border-radius: 12px; background: var(--well); margin-bottom: 1rem; }
    .progress-panel h3 { margin: 0; }
    .progress-panel progress { width: 100%; accent-color: var(--signal); }
    .progress-panel .result { color: var(--ink); font-size: 1rem; }
    .status { margin-top: 1rem; color: var(--ink); }
    footer { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.75rem; border-top: 1px solid var(--line); }
    @media (max-width: 540px) {
      header, footer, .body { padding: 1rem; }
      .fields { grid-template-columns: minmax(0, 1fr); }
      footer button { flex: 1 1 auto; }
    }
  `];

  protected firstUpdated(): void {
    this.renderRoot.querySelector<HTMLDialogElement>("dialog")!.showModal();
    void this.reconnectCalibration();
  }

  protected updated(changed: PropertyValues<this>): void {
    if (changed.has("measuring") && !this.measuring && this.measurementStarted) this.stopProgress();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    clearTimeout(this.pollTimer);
    this.stopProgress();
  }

  private startProgress(startedAt = Date.now()): void {
    this.stopProgress();
    this.startedAt = startedAt;
    this.elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    this.progressTimer = setInterval(() => {
      this.elapsedSeconds = Math.floor((Date.now() - this.startedAt) / 1000);
    }, 1000);
    this.renderRoot.querySelector(".body")?.scrollTo?.({ top: 0 });
  }

  private stopProgress(): void {
    clearInterval(this.progressTimer);
    this.progressTimer = undefined;
  }

  private formatDuration(seconds: number): string {
    return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }

  private renderProgress() {
    if (!this.busy && !this.measurementStarted) return nothing;
    const active = this.busy || this.measuring;
    return html`<section class="progress-panel" aria-label="Measurement progress" aria-busy=${active}>
      <h3>${this.busy ? "Calibrating dummy load…" : this.measuring ? "Measuring standby…" : "Standby result"}</h3>
      ${active ? html`
        <progress aria-label=${this.busy ? "Calibrating dummy load" : "Measuring standby"}></progress>
        <p>Elapsed: ${this.formatDuration(this.elapsedSeconds)}</p>
        ${this.busy ? html`<p>${this.message || "You can close this dialog and reopen it to check progress."}</p>` : nothing}
        <p>${this.busy
          ? "Calibration uses 10-minute stability checks and may repeat until the load is stable. Keep only the warmed-up dummy load connected."
          : `Allow about ${this.formatDuration(this.expectedSeconds)} for settling and sampling. Meter updates and retries can take longer.`}</p>
        ${!this.busy && this.elapsedSeconds > this.expectedSeconds ? html`<p>Still waiting for the meter to finish. Your standby value will update when a reliable reading is returned.</p>` : nothing}
      ` : html`
        <p class="result" role="status">${this.measurementMessage}</p>
        <p>Elapsed: ${this.formatDuration(this.elapsedSeconds)}</p>
      `}
    </section>`;
  }

  private close(): void {
    if (this.measuring) return;
    this.renderRoot.querySelector<HTMLDialogElement>("dialog")!.close();
  }

  private handleClose(): void {
    emit(this, "standby-close");
  }

  render() {
    const controller = this.request.controller;
    const entities = controller.type === "hass_multi" ? controller.entity_ids.join(", ") : controller.type === "hass" ? controller.entity_id : "";
    return html`<dialog aria-labelledby="standby-title" aria-describedby="standby-description"
      @close=${this.handleClose}
      @cancel=${(event: Event) => { if (this.measuring) event.preventDefault(); }}>
      <header>
        <h2 id="standby-title" tabindex="-1" autofocus>Standby measurement setup</h2>
        <p id="standby-description">Adjust the setup for this reading. Your original light measurements are preserved.</p>
      </header>
      <div class="body">
      ${this.request.power_meter.type === "dummy" || this.request.controller.type === "dummy" ? html`<p class="notice warning">Results are simulated for testing; do not submit them as real measurements.</p>` : nothing}
      ${this.renderProgress()}
      <fieldset ?hidden=${this.measurementStarted} ?disabled=${this.busy || this.measuring || this.checkingCalibration} @input=${(event: Event) => event.stopPropagation()} @change=${(event: Event) => event.stopPropagation()}>
        <section aria-label="Devices and meter">
        <h3>Devices and meter</h3>
        <div class="fields">
        ${entities ? html`<label class="wide"><span>Controlled light entities (comma separated)</span><input name="entities" .value=${entities} /></label>` : nothing}
        <label><span>Number of bulbs</span><input name="bulbs" type="number" min="1" max="100" required .value=${String(this.request.multiple_light_count)} /></label>
        ${this.request.power_meter.type === "hass" ? html`
          <label><span>Power sensor</span><input name="power" @change=${this.meterChanged} required .value=${this.request.power_meter.entity_id} /></label>
          <label><span>Voltage sensor (required for a dummy load)</span><input name="voltage" @change=${this.meterChanged} .value=${this.request.power_meter.voltage_entity_id ?? ""} /></label>` : nothing}
        </div>
        </section>
        <section aria-label="Sampling">
        <h3>Sampling</h3>
        <div class="fields timing">
        ${this.timing("sleep_standby", "Standby settling time (seconds)", 0, 10)}
        ${this.timing("sample_count", "Samples", 1, 5)}
        ${this.timing("sleep_time_sample", "Time between samples (seconds)", 0, 2)}
        </div>
        </section>
        <section aria-label="Dummy load">
        <h3>Dummy load</h3>
        <label><span>Resistive dummy load</span><select name="load" .value=${this.loadMode} @change=${this.changeLoad}>
          <option value="original">Keep original setup${this.request.dummy_load ? `: ${this.request.dummy_load.description}` : " (no dummy load)"}</option>
          ${this.savedCalibration ? html`<option value="reuse">Reuse saved calibration: ${this.savedCalibration.description}</option>` : nothing}
          <option value="none">No dummy load</option>
          <option value="calibrate">Add or change dummy load</option>
        </select></label>
        ${this.loadMode === "calibrate" ? html`<div class="calibration">
          <label><span>Dummy-load description</span><input name="description" required maxlength="200" .value=${this.request.dummy_load?.description ?? ""} /></label>
          <p>Preheat the resistive dummy load until stable. Disconnect all measured bulbs and connect only the dummy load to the meter before calibration.</p>
          <button type="button" @click=${this.calibrateLoad}>Calibrate dummy load</button>
        </div>` : nothing}
        </section>
        <div class="instructions">
        <p>Before measuring, connect the selected bulbs${this.loadMode === "calibrate" || this.loadMode === "reuse" || (this.loadMode === "original" && this.request.dummy_load) ? " in parallel with the same preheated dummy load, keeping it connected" : ""}. Confirm there are no other changing loads.</p>
        <p>The selected lights will turn off and stay off. Stale readings may trigger brief full-brightness on/off pulses. No LUT measurements will be rerun.</p>
        </div>
      </fieldset>
      <p class="status" role="status" ?hidden=${this.busy || this.measurementStarted || !this.message}>${this.message}</p>
      </div>
      <footer>
        ${this.busy ? html`<button type="button" @click=${this.close}>Close</button><button type="button" @click=${this.cancelCalibration}>Cancel calibration</button>` : this.measurementStarted && !this.measuring ? html`
          <button type="button" @click=${this.showSetup}>Measure again</button>
          <button type="button" class="primary" @click=${this.close}>Done</button>
        ` : html`
          <button type="button" ?disabled=${this.busy || this.measuring || this.checkingCalibration} @click=${this.close}>Cancel</button>
          <button type="button" class="primary" ?disabled=${this.busy || this.measuring || this.checkingCalibration} @click=${this.measure}>${this.measuring ? "Measuring standby…" : "Confirm and measure standby"}</button>
        `}
      </footer>
    </dialog>`;
  }

  private timing(name: keyof MeasurementParameters, label: string, min: number, value = this.request.parameters[name]) {
    return html`<label><span>${label}</span><input name=${name} type="number" min=${min} required step="1" .value=${String(value)} /></label>`;
  }

  private showSetup(): void {
    this.measurementStarted = false;
  }

  private changeLoad(event: Event) {
    this.loadMode = (event.target as HTMLSelectElement).value;
    this.message = "";
  }

  private readSetup(): LightMeasurementRequest {
    const value = (name: string) => this.renderRoot.querySelector<HTMLInputElement>(`[name="${name}"]`)?.value.trim() ?? "";
    const setup = structuredClone(this.request);
    for (const input of this.renderRoot.querySelectorAll<HTMLInputElement>("input")) if (!input.reportValidity()) throw new Error("Check the setup fields.");
    setup.multiple_light_count = Number(value("bulbs"));
    if (setup.controller.type === "hass" || setup.controller.type === "hass_multi") {
      const ids = value("entities").split(",").map(id => id.trim()).filter(Boolean);
      const transition_time = setup.controller.transition_time;
      setup.controller = ids.length === 1 ? { type: "hass", entity_id: ids[0]!, transition_time } : { type: "hass_multi", entity_ids: ids, transition_time };
    }
    if (setup.power_meter.type === "hass") {
      setup.power_meter.entity_id = value("power");
      setup.power_meter.voltage_entity_id = value("voltage") || null;
    }
    for (const name of ["sleep_standby", "sample_count", "sleep_time_sample"] as const) setup.parameters[name] = Number(value(name));
    if (this.loadMode === "reuse" && !this.savedCalibration) throw new Error("No compatible saved calibration is available.");
    if (this.loadMode === "reuse" && this.savedCalibration) {
      setup.dummy_load = { mode: "reuse", description: this.savedCalibration.description, resistance: this.savedCalibration.resistance };
    }
    if (this.loadMode === "none") setup.dummy_load = null;
    if (this.loadMode === "calibrate") {
      const description = value("description");
      setup.dummy_load = { mode: "calibrate", description };
    }
    return setup;
  }

  private readMeter(): PowerMeterSpec {
    const meter = structuredClone(this.request.power_meter);
    if (meter.type === "hass") {
      meter.entity_id = this.renderRoot.querySelector<HTMLInputElement>('[name="power"]')!.value.trim();
      meter.voltage_entity_id = this.renderRoot.querySelector<HTMLInputElement>('[name="voltage"]')!.value.trim() || null;
    }
    return meter;
  }

  private async loadSavedCalibration(): Promise<void> {
    const revision = ++this.meterRevision;
    this.savedCalibration = null;
    if (!this.calibrationActions) return;
    this.checkingCalibration = true;
    try {
      const calibration = await this.calibrationActions.loadSaved(this.readMeter());
      if (revision === this.meterRevision) this.savedCalibration = calibration;
    } catch (error) {
      if (revision === this.meterRevision) this.message = error instanceof Error ? error.message : "Could not check saved calibration.";
    } finally {
      if (revision === this.meterRevision) this.checkingCalibration = false;
    }
  }

  private meterChanged(): void {
    if (this.loadMode === "reuse") this.loadMode = "none";
    void this.loadSavedCalibration();
  }

  private async reconnectCalibration(): Promise<void> {
    await this.loadSavedCalibration();
    await this.pollCalibration();
  }

  private async pollCalibration(): Promise<void> {
    if (!this.calibrationActions || !this.isConnected) return;
    try {
      const job = await this.calibrationActions.status(this.sessionId);
      if (!this.isConnected) return;
      if (job) {
        await this.applyCalibrationJob(job);
      } else if (this.busy) {
        this.busy = false;
        this.stopProgress();
        this.message = "Calibration is no longer available. The app may have restarted; start a new calibration.";
      }
    } catch {
      this.message = "Could not refresh calibration status. Retrying…";
      this.pollTimer = setTimeout(() => void this.pollCalibration(), 2000);
    }
  }

  private async applyCalibrationJob(job: CalibrationJob): Promise<void> {
    clearTimeout(this.pollTimer);
    this.calibrationJob = job;
    this.busy = job.status === "running" || job.status === "cancelling";
    if (this.busy) {
      if (!this.progressTimer) this.startProgress(Date.parse(job.started_at));
      this.message = job.status === "cancelling" ? "Cancelling calibration…" : "";
      this.pollTimer = setTimeout(() => void this.pollCalibration(), 1000);
      return;
    }
    this.stopProgress();
    if (job.status === "completed") {
      await this.loadSavedCalibration();
      this.message = "Calibration complete. Reconnect the measured bulbs in parallel, then confirm the standby measurement.";
      if (this.savedCalibration && this.savedCalibration.power_meter_fingerprint === job.calibration?.power_meter_fingerprint) {
        this.loadMode = "reuse";
      } else {
        this.message = "Calibration complete for a different meter. Select that meter to reuse it.";
      }
    } else {
      this.message = job.status === "cancelled" ? "Calibration cancelled." : job.error || "Calibration failed.";
    }
  }

  private async cancelCalibration(): Promise<void> {
    if (!this.calibrationActions || !this.calibrationJob) return;
    try {
      await this.applyCalibrationJob(await this.calibrationActions.cancel(this.sessionId, this.calibrationJob.id));
    } catch (error) {
      this.message = error instanceof Error ? error.message : "Could not cancel calibration. Try again.";
    }
  }

  private async calibrateLoad(): Promise<void> {
    if (this.busy || this.measuring || this.checkingCalibration || !this.calibrationActions) return;
    try {
      const setup = this.readSetup();
      this.busy = true;
      this.message = "";
      const job = await this.calibrationActions.start(this.sessionId, setup);
      if (this.isConnected) await this.applyCalibrationJob(job);
    } catch (error) {
      this.busy = false;
      this.message = error instanceof Error ? error.message : "Could not start calibration.";
      // A lost POST response may still have started the operation.
      await this.pollCalibration();
    }
  }

  private measure() {
    if (this.busy || this.measuring || this.checkingCalibration) return;
    try {
      const setup = this.readSetup();
      if (this.loadMode === "calibrate") throw new Error("Calibrate the dummy load first.");
      this.expectedSeconds = Math.ceil(setup.parameters.sleep_standby + setup.parameters.sample_count * setup.parameters.sleep_time_sample);
      this.measurementStarted = true;
      this.measuring = true;
      this.message = "";
      this.startProgress();
      emit(this, "standby-measure", setup);
    } catch (error) {
      this.message = error instanceof Error ? error.message : "Invalid setup.";
    }
  }
}
