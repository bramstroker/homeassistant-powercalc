import { LitElement, css, html, nothing } from "lit";
import { ApiError, MeasureApiClient, SessionEventStream } from "../api-client";
import type { AppSettings, Capabilities, EntityDescriptor, MeasureDefinition, MeasureType, MeasurementRequest, MeasurementRunRequest, PowerMeterTestResult, PreflightResponse, SessionEvent, SessionFile, SessionSnapshot } from "../types";
import type { ReviewMetric, ReviewRow } from "./preflight-view";
import { sharedStyles } from "../styles";
import "./preflight-view";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

type View = "loading" | "setup" | "review" | "running" | "result" | "settings";

export class AppShell extends LitElement {
  static readonly properties = {
    view: { state: true }, loadingMessage: { state: true }, errorMessage: { state: true }, busy: { state: true },
    connectedToEvents: { state: true }, snapshot: { state: true }, request: { state: true }, preflight: { state: true },
    files: { state: true }, logs: { state: true }, settings: { state: true }, runRequest: { state: true },
    samples: { state: true }, testingPowerMeter: { state: true }, powerMeterTestResult: { state: true },
  };

  view: View = "loading";
  loadingMessage = "Connecting to Home Assistant…";
  errorMessage = "";
  busy = false;
  connectedToEvents = false;
  snapshot?: SessionSnapshot;
  request?: MeasurementRequest;
  runRequest?: MeasurementRunRequest;
  preflight?: PreflightResponse;
  files: SessionFile[] = [];
  logs: string[] = [];
  samples: number[] = [];
  capabilities?: Capabilities;
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  settings?: AppSettings;
  definitions: MeasureDefinition[] = [];
  deviceEntities: Record<string, EntityDescriptor[]> = {};
  testingPowerMeter = false;
  powerMeterTestResult?: PowerMeterTestResult;

  private readonly api = new MeasureApiClient();
  private eventStream?: SessionEventStream;
  private settingsReturnView: View = "setup";

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-height: 100vh; background: var(--canvas); }
    .shell { width: min(1320px, calc(100% - 2rem)); margin: 0 auto; padding: clamp(1rem, 3vw, 2rem) 0 4rem; }
    header { margin-bottom: clamp(1.5rem, 4vw, 2.5rem); }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--line); }
    .brand { display: flex; align-items: center; gap: 0.7rem; color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.16em; text-transform: uppercase; }
    .brand-logo { width: 20px; height: 24px; object-fit: contain; }
    .intro { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.78fr); gap: 1.25rem clamp(1.5rem, 5vw, 4rem); align-items: end; padding-top: clamp(1.5rem, 4vw, 2.5rem); }
    h1 { grid-column: 1 / -1; margin: 0; font-size: clamp(2rem, 3.4vw, 3rem); line-height: 1; letter-spacing: -0.04em; }
    .subtitle { max-width: 540px; margin: 0.8rem 0 0; color: var(--muted); font-size: 1rem; line-height: 1.6; }
    .settings-toggle { min-height: 36px; padding: 0.4rem 0.8rem; border-radius: 999px; font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 0.45rem; }
    .settings-toggle::before { content: "⚙"; font-size: 0.95rem; }
    .sequence { margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.45rem; list-style: none; }
    .sequence > li { position: relative; display: grid; gap: 0.45rem; min-width: 0; color: var(--muted); font: 700 0.68rem/1.15 ui-monospace, monospace; letter-spacing: 0.08em; text-transform: uppercase; }
    .sequence > li:not(:last-child)::after { content: ""; position: absolute; top: 10px; left: calc(20px + 0.45rem); width: calc(100% - 40px - 0.45rem); height: 2px; border-radius: 99px; background: var(--line); }
    .step-number { display: grid; place-items: center; width: 20px; height: 20px; border: 1px solid var(--line); border-radius: 50%; background: var(--canvas); color: var(--muted); font-size: 0.66rem; z-index: 1; }
    .sequence > li.active { color: var(--ink); } .sequence > li.done { color: var(--signal-strong); }
    .sequence > li.active .step-number { border-color: var(--signal); box-shadow: 0 0 0 4px color-mix(in srgb, var(--signal) 16%, transparent); color: var(--on-signal); background: var(--signal); }
    .sequence > li.done .step-number { border-color: var(--signal); color: var(--on-signal); background: var(--signal); }
    .sequence > li.done:not(:last-child)::after { background: var(--signal); }
    .loading { min-height: 260px; display: grid; place-items: center; text-align: center; }
    .pulse { width: 40px; height: 40px; margin: 0 auto 1rem; border: 2px solid var(--line); border-top-color: var(--signal); border-radius: 50%; animation: spin 850ms linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    footer { margin-top: 1rem; color: var(--muted); font-size: 0.72rem; text-align: right; }
    @media (max-width: 700px) { .intro { grid-template-columns: 1fr; } h1 { grid-column: auto; } .sequence { max-width: 560px; } }
    @media (max-width: 460px) { .shell { width: min(100% - 1.25rem, 980px); } .sequence { gap: 0.3rem; } .sequence > li { font-size: 0.58rem; letter-spacing: 0.04em; } .sequence > li:not(:last-child)::after { left: calc(20px + 0.3rem); width: calc(100% - 40px - 0.3rem); } }
  `];

  connectedCallback(): void { super.connectedCallback(); void this.boot(); }
  disconnectedCallback(): void { this.eventStream?.close(); super.disconnectedCallback(); }

  render() {
    return html`
      <main class="shell">
        <header>
          <div class="topbar">
            <div class="brand"><img class="brand-logo" src="powercalc-logo.svg" alt="" />Powercalc Measure</div>
            <button class="settings-toggle" type="button" @click=${this.openSettings} ?disabled=${this.view === "loading" || this.view === "settings"}>Settings</button>
          </div>
          <div class="intro">
            <h1>Turn real watts into a precise profile.</h1>
            <div>
            <p class="subtitle">Configure, validate, and monitor a power measurement without leaving Home Assistant.</p>
            </div>
            <nav aria-label="Measurement progress">
              <ol class="sequence">
                ${["Set up", "Review", "Measure", "Result"].map((step, index) => html`<li class=${this.stepClass(index)} aria-current=${index === this.currentStep() ? "step" : nothing}><span class="step-number">${index < this.currentStep() ? "✓" : index + 1}</span><span>${step}</span></li>`)}
              </ol>
            </nav>
          </div>
        </header>
        ${this.renderView()}
        <footer>Keep this app running while the measurement is in progress.</footer>
      </main>
    `;
  }

  private renderLoading() {
    return html`
      <section class="panel loading" aria-live="polite"><div><div class="pulse" aria-hidden="true"></div><p>${this.loadingMessage}</p>${this.errorMessage ? this.renderRetry() : nothing}</div></section>`;
  }

  private renderRetry() {
    return html`<p class="error" role="alert">${this.errorMessage}</p><button @click=${this.boot}>Retry</button>`;
  }

  private renderView() {
    if (this.view === "loading") return this.renderLoading();
    if (this.view === "settings") return html`
      <measure-settings-view .powers=${this.powers} .settings=${this.settings} .busy=${this.busy} .testing=${this.testingPowerMeter} .testResult=${this.powerMeterTestResult} .errorMessage=${this.errorMessage} @back=${this.closeSettings} @save=${this.saveSettings} @test=${this.testPowerMeter}></measure-settings-view>`;
    if (this.view === "review" && this.preflight && (this.request || this.runRequest)) return html`
      <measure-preflight-view .metrics=${this.reviewMetrics()} .summary=${this.reviewSummary()} .warnings=${this.preflight.warnings} .canOverwrite=${this.reviewCanOverwrite()} .busy=${this.busy} .errorMessage=${this.errorMessage} @back=${this.backToSetup} @start=${this.start}></measure-preflight-view>`;
    if (this.view === "running" && this.snapshot) return html`
      <measure-running-view .snapshot=${this.snapshot} .connected=${this.connectedToEvents} .logs=${this.logs} .samples=${this.samples} .busy=${this.busy} @cancel=${this.cancel} @confirm=${this.confirm}></measure-running-view>`;
    if (this.view === "result" && this.snapshot) return html`
      <measure-result-view .snapshot=${this.snapshot} .files=${this.files} .fileUrl=${(name: string) => this.api.fileUrl(name)} .downloadAll=${this.downloadAllFiles.bind(this)} .busy=${this.busy} .errorMessage=${this.errorMessage} @new=${this.newMeasurement} @resume=${this.resume}></measure-result-view>`;
    return html`
      <measure-setup-view
        .capabilities=${this.capabilities} .definitions=${this.definitions}
        .lights=${this.lights} .powers=${this.powers} .voltages=${this.voltages} .deviceEntities=${this.deviceEntities}
        .initialType=${this.pendingType()} .initialRequest=${this.request} .initialRunRequest=${this.runRequest}
        .defaultPowerEntityId=${this.settings?.default_power_entity_id ?? ""} .defaultMeasureDevice=${this.settings?.default_measure_device ?? ""} .powerMeter=${this.settings?.power_meter ?? "hass"}
        .busy=${this.busy} .errorMessage=${this.errorMessage}
        @preflight=${this.runPreflight} @preflight-run=${this.runPreflightRun}></measure-setup-view>`;
  }

  private pendingType(): MeasureType | undefined {
    if (this.runRequest) return this.runRequest.measure_type;
    if (this.request) return "Light bulb(s)";
    return undefined;
  }

  private reviewMetrics(): ReviewMetric[] {
    if (!this.request || !this.preflight) return [];
    const duration = this.preflight.estimated_duration_seconds;
    return [
      { label: "Variations", value: String(this.preflight.estimated_variations ?? "—") },
      { label: "Estimated time", value: duration === undefined ? "—" : this.duration(duration) },
      { label: "Modes", value: String(this.request.modes.length) },
    ];
  }

  private reviewSummary(): ReviewRow[] {
    if (this.request) {
      return [
        { label: "Model", value: `${this.request.product_name} (${this.request.model_id})` },
        { label: "Light", value: this.request.light_entity_id },
        { label: "Power", value: this.request.power_entity_id || "Configured power meter" },
        { label: "Modes", value: this.request.modes.join(", ") },
      ];
    }
    if (this.runRequest) {
      const rows: ReviewRow[] = [{ label: "Type", value: this.runRequest.measure_type }];
      if (this.runRequest.measure_device) rows.push({ label: "Device", value: this.runRequest.measure_device });
      const power = this.runRequest.answers.powermeter_entity_id;
      if (typeof power === "string" && power && power !== "__managed__") rows.push({ label: "Power", value: power });
      return rows;
    }
    return [];
  }

  private reviewCanOverwrite(): boolean {
    return this.request?.resume_policy === "overwrite";
  }

  private duration(seconds: number): string {
    if (seconds < 60) return `${Math.ceil(seconds)} sec`;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.ceil((seconds % 3600) / 60);
    return hours ? `${hours} hr ${minutes} min` : `${minutes} min`;
  }

  private async boot(): Promise<void> {
    this.view = "loading"; this.errorMessage = "";
    try {
      const currentPromise = this.api.getCurrent().catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return { state: "idle" } satisfies SessionSnapshot;
        throw error;
      });
      [this.capabilities, this.lights, this.powers, this.voltages, this.settings, this.snapshot, this.definitions] = await Promise.all([
        this.api.getCapabilities(), this.api.getEntities("light"), this.api.getEntities("power"), this.api.getEntities("voltage"), this.api.getSettings(), currentPromise, this.api.getMeasureDefinitions(),
      ]);
      await this.loadDeviceEntities();
      this.request = this.snapshot.request;
      await this.routeSnapshot();
    } catch (error) { this.errorMessage = this.message(error); }
  }

  private async loadDeviceEntities(): Promise<void> {
    // Devices for the non-light measurement types (media_player, fan, vacuum, …).
    // Lights are already fetched separately, and "sensor" is handled by the power selectors.
    const domains = [...new Set(
      this.definitions
        .flatMap((definition) => definition.fields)
        .filter((field) => field.control === "entity" && field.entity_domain && field.entity_domain !== "sensor" && field.entity_domain !== "light")
        .map((field) => field.entity_domain as string),
    )];
    const lists = await Promise.all(domains.map((domain) => this.api.getEntitiesByDomain(domain).catch(() => [] as EntityDescriptor[])));
    const entities: Record<string, EntityDescriptor[]> = {};
    domains.forEach((domain, index) => { entities[domain] = lists[index] ?? []; });
    this.deviceEntities = entities;
  }

  private async routeSnapshot(): Promise<void> {
    const state = this.snapshot?.state ?? "idle";
    if (["running", "awaiting_confirmation", "cancelling", "validating", "ready"].includes(state)) { this.view = "running"; this.connectEvents(); return; }
    if (["completed", "failed", "cancelled", "resumable"].includes(state)) { this.view = "result"; await this.loadFiles(); return; }
    this.view = "setup";
  }

  private runPreflight(event: CustomEvent<MeasurementRequest>): void { void this.preflightRequest(event.detail); }
  private runPreflightRun(event: CustomEvent<MeasurementRunRequest>): void { void this.preflightRunRequest(event.detail); }
  private async preflightRequest(request: MeasurementRequest): Promise<void> {
    this.busy = true; this.errorMessage = ""; this.request = request; this.runRequest = undefined;
    try { this.preflight = await this.api.preflight(request); this.view = "review"; }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private async preflightRunRequest(request: MeasurementRunRequest): Promise<void> {
    this.busy = true; this.errorMessage = ""; this.runRequest = request; this.request = undefined;
    try { this.preflight = await this.api.preflightRun(request); this.view = "review"; }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private backToSetup(): void { this.errorMessage = ""; this.view = "setup"; }
  private start(): void { void this.startRequest(); }
  private async startRequest(): Promise<void> {
    this.busy = true; this.errorMessage = ""; this.samples = [];
    try {
      this.snapshot = this.runRequest ? await this.api.startRun(this.runRequest) : this.request ? await this.api.start(this.request) : undefined;
      if (!this.snapshot) return;
      this.view = "running"; this.connectEvents();
    }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }

  private connectEvents(): void {
    this.eventStream?.close();
    this.eventStream = new SessionEventStream(this.api.eventsUrl(), (event) => this.consumeEvent(event),
      (connected) => { this.connectedToEvents = connected; }, () => { void this.refreshSnapshot(); });
    this.eventStream.connect();
  }

  private consumeEvent(event: SessionEvent): void {
    if (event.message && (event.type === "log" || event.type === "checkpoint")) this.logs = [...this.logs.slice(-39), event.message];
    if (event.type === "sample" && typeof event.power === "number") this.samples = [...this.samples.slice(-179), event.power];
    if (event.snapshot) this.snapshot = event.snapshot;
    if (this.snapshot && this.isTerminal(this.snapshot.state)) void this.enterResult();
  }

  private async refreshSnapshot(): Promise<void> {
    try {
      this.snapshot = await this.api.getCurrent();
      if (this.isTerminal(this.snapshot.state)) await this.enterResult();
    }
    catch { this.connectedToEvents = false; }
  }

  private isTerminal(state: SessionSnapshot["state"]): boolean {
    return ["completed", "failed", "cancelled", "resumable"].includes(state);
  }

  private async enterResult(): Promise<void> {
    this.eventStream?.close();
    this.connectedToEvents = false;
    // If the user is on the settings view when a session finishes, don't yank them
    // away — send them to the result view only once they close settings.
    if (this.view === "settings") this.settingsReturnView = "result";
    else this.view = "result";
    await this.loadFiles();
  }
  private cancel(): void { void this.cancelRequest(); }
  private confirm(): void { void this.confirmRequest(); }
  private async confirmRequest(): Promise<void> {
    this.busy = true;
    try { this.snapshot = await this.api.confirm(); }
    catch (error) { this.logs = [...this.logs, `Confirmation failed: ${this.message(error)}`]; }
    finally { this.busy = false; }
  }
  private async cancelRequest(): Promise<void> {
    this.busy = true;
    try { this.snapshot = await this.api.cancel(); }
    catch (error) { this.logs = [...this.logs, `Cancellation failed: ${this.message(error)}`]; }
    finally { this.busy = false; }
  }
  private async loadFiles(): Promise<void> { try { this.files = await this.api.getFiles(); } catch { this.files = []; } }
  private downloadAllFiles(): void {
    for (const file of this.files) {
      const anchor = document.createElement("a");
      anchor.href = this.api.fileUrl(file.name);
      anchor.download = file.name.split("/").pop() ?? file.name;
      anchor.rel = "noopener";
      anchor.style.display = "none";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
    }
  }
  private newMeasurement(): void {
    this.eventStream?.close(); this.snapshot = { state: "idle" }; this.request = undefined; this.runRequest = undefined; this.preflight = undefined;
    this.files = []; this.logs = []; this.samples = []; this.errorMessage = ""; this.view = "setup";
  }
  private resume(): void { void this.resumeRequest(); }
  private async resumeRequest(): Promise<void> {
    this.busy = true; this.errorMessage = "";
    try { this.snapshot = await this.api.resume(); this.view = "running"; this.connectEvents(); }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private openSettings(): void {
    if (this.view === "loading" || this.view === "settings") return;
    this.settingsReturnView = this.view;
    this.errorMessage = ""; this.powerMeterTestResult = undefined; this.view = "settings";
  }
  private closeSettings(): void { this.errorMessage = ""; this.view = this.settingsReturnView; }
  private testPowerMeter(event: CustomEvent<AppSettings>): void { void this.testPowerMeterRequest(event.detail); }
  private async testPowerMeterRequest(settings: AppSettings): Promise<void> {
    this.testingPowerMeter = true; this.powerMeterTestResult = undefined;
    try { this.powerMeterTestResult = await this.api.testPowerMeter(settings); }
    catch (error) { this.powerMeterTestResult = { success: false, message: this.message(error) }; }
    finally { this.testingPowerMeter = false; }
  }
  private saveSettings(event: CustomEvent<AppSettings>): void { void this.saveSettingsRequest(event.detail); }
  private async saveSettingsRequest(settings: AppSettings): Promise<void> {
    this.busy = true; this.errorMessage = "";
    try { this.settings = await this.api.saveSettings(settings); this.view = this.settingsReturnView; }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private stepClass(index: number): string {
    const current = this.currentStep();
    if (index === current) return "active";
    if (index < current) return "done";
    return "";
  }
  private currentStep(): number { return { loading: 0, setup: 0, review: 1, running: 2, result: 3, settings: 0 }[this.view]; }
  private message(error: unknown): string { return error instanceof Error ? error.message : "Something went wrong. Try again."; }
}

customElements.define("powercalc-measure-app", AppShell);
