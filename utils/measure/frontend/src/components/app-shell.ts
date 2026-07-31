import { LitElement, css, html, nothing } from "lit";
import { MeasureApiClient, SessionEventStream } from "../api-client";
import { MeasureAppController } from "../app-controller";
import type { AppView, MeasureAppApi, MeasureAppState } from "../app-controller";
import { requestFieldValue } from "../measurement-kinds";
import type { AppSettings, Capabilities, ContributionAuthDeviceStatus, ContributionAuthState, ContributionDeviceFlow, ContributionPreview, ContributionPreviewRequest, ContributionResult, ContributionSubmitRequest, DummyLoadCalibration, EntityDescriptor, FormField, MeasureDefinition, MeasureType, MeasurementRequest, PlotCollection, PowerMeterDiagnostic, PreflightResponse, SessionFile, SessionSnapshot, SettingsSection, ShellyDiscoveryDevice } from "../types";
import type { ReviewMetric, ReviewRow } from "./preflight-view";
import { sharedStyles } from "../styles";
import "./preflight-view";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

const POWERCALC_LOGO_URL = new URL("../assets/powercalc-logo.svg", import.meta.url).href;

export class AppShell extends LitElement implements MeasureAppState {
  static readonly properties = {
    view: { state: true }, settingsSection: { state: true }, loadingMessage: { state: true }, errorMessage: { state: true }, busy: { state: true },
    connectedToEvents: { state: true }, snapshot: { state: true }, request: { state: true }, preflight: { state: true },
    files: { state: true }, plotCollection: { state: true }, logs: { state: true }, settings: { state: true },
    contributionAuth: { state: true }, contributionDeviceFlow: { state: true }, contributionDeviceStatus: { state: true },
    contributionDraft: { state: true }, contributionPreview: { state: true }, contributionResult: { state: true },
    contributionBusy: { state: true }, contributionAuthBusy: { state: true }, contributionError: { state: true }, contributionAuthError: { state: true },
    samples: { state: true }, testingPowerMeter: { state: true }, powerMeterTestResult: { state: true },
    deviceEntities: { state: true }, deviceEntityErrors: { state: true },
    dummyLoadCalibration: { state: true }, dummyLoadCalibrationError: { state: true },
    shellyDiscoveryDevices: { state: true }, discoveringShellys: { state: true }, shellyDiscoveryError: { state: true },
    shellyDiscoveryAvailable: { state: true }, shellyDiscoveryMessage: { state: true },
  };

  view: AppView = "loading";
  settingsSection?: SettingsSection;
  loadingMessage = "Connecting to Home Assistant…";
  errorMessage = "";
  busy = false;
  connectedToEvents = false;
  snapshot?: SessionSnapshot;
  request?: MeasurementRequest;
  selectedMeasureType?: MeasureType;
  preflight?: PreflightResponse;
  files: SessionFile[] = [];
  plotCollection: PlotCollection = { partial: false, plots: [], warnings: [] };
  logs: string[] = [];
  samples: number[] = [];
  capabilities?: Capabilities;
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  dummyLoadCalibration: DummyLoadCalibration | null = null;
  dummyLoadCalibrationError = "";
  settings?: AppSettings;
  contributionAuth?: ContributionAuthState;
  contributionDeviceFlow?: ContributionDeviceFlow;
  contributionDeviceStatus?: ContributionAuthDeviceStatus;
  contributionDraft?: ContributionPreview;
  contributionPreview?: ContributionPreview;
  contributionResult?: ContributionResult;
  contributionBusy = false;
  contributionAuthBusy = false;
  contributionError = "";
  contributionAuthError = "";
  definitions: MeasureDefinition[] = [];
  deviceEntities: Record<string, EntityDescriptor[]> = {};
  deviceEntityErrors: Record<string, string> = {};
  testingPowerMeter = false;
  powerMeterTestResult?: PowerMeterDiagnostic;
  shellyDiscoveryDevices: ShellyDiscoveryDevice[] = [];
  discoveringShellys = false;
  shellyDiscoveryError = "";
  shellyDiscoveryAvailable?: boolean;
  shellyDiscoveryMessage?: string | null;

  private readonly api: MeasureAppApi & Pick<MeasureApiClient, "diagnosticsUrl" | "fileUrl" | "eventsUrl"> = new MeasureApiClient();
  private readonly controller = new MeasureAppController(
    this,
    () => this.api,
    ({ onEvent, onConnection, onReconnect }) => new SessionEventStream(this.api.eventsUrl(), onEvent, onConnection, onReconnect),
    () => this.requestUpdate(),
  );

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-height: 100vh; background: var(--canvas); }
    .shell { width: min(1320px, calc(100% - 2rem)); margin: 0 auto; padding: clamp(1rem, 3vw, 2rem) 0 4rem; }
    header { margin-bottom: clamp(1.5rem, 4vw, 2.5rem); }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--line); }
    .brand { display: flex; align-items: center; gap: 0.7rem; color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.16em; text-transform: uppercase; }
    .brand-logo { width: 20px; height: 24px; object-fit: contain; }
    .version { color: var(--muted); font: 500 0.68rem/1 ui-monospace, monospace; letter-spacing: normal; text-transform: none; white-space: nowrap; }
    .intro { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.78fr); gap: 1.25rem clamp(1.5rem, 5vw, 4rem); align-items: end; padding-top: clamp(1.5rem, 4vw, 2.5rem); }
    h1 { grid-column: 1 / -1; margin: 0; font-size: clamp(2rem, 3.4vw, 3rem); line-height: 1; letter-spacing: -0.04em; }
    .subtitle { max-width: 540px; margin: 0.8rem 0 0; color: var(--muted); font-size: 1rem; line-height: 1.6; }
    .settings-toggle { min-height: 36px; padding: 0.4rem 0.8rem; border-radius: 999px; font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 0.45rem; }
    .settings-toggle::before { content: "⚙"; font-size: 0.95rem; }
    .sequence { margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.45rem; list-style: none; }
    .sequence > li { position: relative; display: grid; gap: 0.45rem; min-width: 0; color: var(--muted); font: 700 0.68rem/1.15 ui-monospace, monospace; letter-spacing: 0.08em; text-transform: uppercase; }
    .sequence > li:not(:last-child)::after { content: ""; position: absolute; top: 10px; left: calc(20px + 0.45rem); width: calc(100% - 40px - 0.45rem); height: 2px; border-radius: 99px; background: var(--line); }
    .step-number { display: grid; place-items: center; width: 20px; height: 20px; border: 1px solid var(--line); border-radius: 50%; background: var(--canvas); color: var(--muted); font-size: 0.66rem; z-index: 1; }
    .calibration-warning { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
    .calibration-warning button { flex: 0 0 auto; }
    .sequence > li.active { color: var(--ink); } .sequence > li.done { color: var(--signal-strong); }
    .sequence > li.active .step-number { border-color: var(--signal); box-shadow: 0 0 0 4px color-mix(in srgb, var(--signal) 16%, transparent); color: var(--on-signal); background: var(--signal); }
    .sequence > li.done .step-number { border-color: var(--signal); color: var(--on-signal); background: var(--signal); }
    .sequence > li.done:not(:last-child)::after { background: var(--signal); }
    .loading { min-height: 260px; display: grid; place-items: center; text-align: center; }
    .pulse { width: 40px; height: 40px; margin: 0 auto 1rem; border: 2px solid var(--line); border-top-color: var(--signal); border-radius: 50%; animation: spin 850ms linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    footer { margin-top: 1rem; color: var(--muted); font-size: 0.72rem; text-align: right; }
    @media (max-width: 700px) { .intro { grid-template-columns: 1fr; } h1 { grid-column: auto; } .sequence { max-width: 560px; } .calibration-warning { align-items: flex-start; flex-direction: column; } }
    @media (max-width: 460px) { .shell { width: min(100% - 1.25rem, 980px); } .sequence { gap: 0.3rem; } .sequence > li { font-size: 0.58rem; letter-spacing: 0.04em; } .sequence > li:not(:last-child)::after { left: calc(20px + 0.3rem); width: calc(100% - 40px - 0.3rem); } }
  `];

  connectedCallback(): void { super.connectedCallback(); void this.boot(); }
  disconnectedCallback(): void { this.controller.dispose(); super.disconnectedCallback(); }

  render() {
    return html`
      <main class="shell">
        <header>
          <div class="topbar">
            <div class="brand">
              <img class="brand-logo" src=${POWERCALC_LOGO_URL} alt="" />
              <span>Powercalc Measure</span>
              ${this.capabilities?.runtime_version
                ? html`<span class="version">Version ${this.displayVersion()}</span>`
                : nothing}
            </div>
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
        ${this.dummyLoadCalibrationError ? html`
          <div class="notice calibration-warning" role="status">
            <span>${this.dummyLoadCalibrationError}</span>
            <button type="button" @click=${this.retryDummyLoadCalibration}>Retry</button>
          </div>
        ` : nothing}
        ${this.renderView()}
        <footer>Keep this app running while the measurement is in progress.</footer>
      </main>
    `;
  }

  private renderLoading() {
    return html`
      <section class="panel loading" aria-live="polite"><div><div class="pulse" aria-hidden="true"></div><p>${this.loadingMessage}</p>${this.errorMessage ? this.renderRetry() : nothing}</div></section>`;
  }

  private displayVersion(): string {
    return this.capabilities?.runtime_version.replace(/:app$/, "") ?? "";
  }

  private renderRetry() {
    return html`<p class="error" role="alert">${this.errorMessage}</p><button @click=${this.boot}>Retry</button>`;
  }

  private renderView() {
    if (this.view === "loading") return this.renderLoading();
    if (this.view === "settings") return html`
      <measure-settings-view
        .powers=${this.powers} .settings=${this.settings} .capabilities=${this.capabilities}
        .busy=${this.busy} .testing=${this.testingPowerMeter} .testResult=${this.powerMeterTestResult} .errorMessage=${this.errorMessage}
        .shellyDiscoveryDevices=${this.shellyDiscoveryDevices} .discoveringShellys=${this.discoveringShellys}
        .shellyDiscoveryError=${this.shellyDiscoveryError} .shellyDiscoveryAvailable=${this.shellyDiscoveryAvailable}
        .shellyDiscoveryMessage=${this.shellyDiscoveryMessage}
        .contributionAuth=${this.contributionAuth} .contributionDeviceFlow=${this.contributionDeviceFlow}
        .contributionDeviceStatus=${this.contributionDeviceStatus} .contributionAuthBusy=${this.contributionAuthBusy}
        .contributionAuthError=${this.contributionAuthError} .initialSection=${this.settingsSection}
        @back=${this.closeSettings} @save=${this.saveSettings} @test=${this.testPowerMeter} @test-clear=${this.clearPowerMeterTestResult}
        @shelly-discover=${this.discoverShellys} @github-device-start=${this.startContributionDeviceAuth}
        @github-token-save=${this.saveContributionToken} @github-disconnect=${this.disconnectContributionAuth}></measure-settings-view>`;
    if (this.view === "review" && this.preflight && this.request) return html`
      <measure-preflight-view .metrics=${this.reviewMetrics()} .summary=${this.reviewSummary()} .warnings=${this.preflight.warnings} .powerMeterDiagnostic=${this.preflight.power_meter_diagnostic} .canOverwrite=${this.reviewCanOverwrite()} .confirmationAction=${this.confirmationAction()} .busy=${this.busy} .errorMessage=${this.errorMessage} @back=${this.backToSetup} @start=${this.start}></measure-preflight-view>`;
    if (this.view === "running" && this.snapshot) return html`
      <measure-running-view .snapshot=${this.snapshot} .confirmationAction=${this.confirmationAction()} .warningConfirmation=${this.confirmationIsWarning()} .connected=${this.connectedToEvents} .logs=${this.logs} .samples=${this.samples} .diagnosticsUrl=${this.api.diagnosticsUrl()} .busy=${this.busy} @cancel=${this.cancel} @confirm=${this.confirm}></measure-running-view>`;
    if (this.view === "result" && this.snapshot) return html`
      <measure-result-view .snapshot=${this.snapshot} .files=${this.files} .plotCollection=${this.plotCollection} .fileUrl=${(name: string) => this.api.fileUrl(name)} .downloadAll=${this.downloadAllFiles.bind(this)} .diagnosticsUrl=${this.api.diagnosticsUrl()} .busy=${this.busy} .canResume=${this.canResumeSession()} .errorMessage=${this.errorMessage} .contributionAuth=${this.contributionAuth} .contributionDraft=${this.contributionDraft} .contributionPreview=${this.contributionPreview} .contributionResult=${this.contributionResult} .contributionBusy=${this.contributionBusy} .contributionError=${this.contributionError} @new=${this.newMeasurement} @resume=${this.resume} @open-settings=${this.openSettings} @contribution-preview=${this.previewContribution} @contribution-submit=${this.submitContribution}></measure-result-view>`;
    return html`
      <measure-setup-view
        .capabilities=${this.capabilities} .definitions=${this.definitions}
        .lights=${this.lights} .powers=${this.powers} .voltages=${this.voltages} .deviceEntities=${this.deviceEntities} .deviceEntityErrors=${this.deviceEntityErrors}
        .initialType=${this.pendingType()} .initialRequest=${this.request}
        .dummyLoadCalibration=${this.dummyLoadCalibration}
        .defaultPowerEntityId=${this.settings?.default_power_entity_id ?? ""} .defaultMeasureDevice=${this.settings?.default_measure_device ?? ""} .powerMeter=${this.settings?.power_meter ?? "hass"} .shellyIp=${this.settings?.shelly_ip ?? ""} .shellyUsername=${this.settings?.shelly_username ?? "admin"} .kasaIp=${this.settings?.kasa_ip ?? ""}
        .powerMeterConfigured=${this.powerMeterConfigured()}
        .busy=${this.busy} .errorMessage=${this.errorMessage}
        @preflight=${this.runPreflight} @measure-type-selected=${this.measureTypeSelected} @entity-domains-requested=${this.entityDomainsRequested} @open-settings=${this.openSettings}></measure-setup-view>`;
  }

  private powerMeterConfigured(): boolean {
    if (!this.settings?.power_meter) return false;
    if (!this.settings.default_measure_device) return false;
    if (this.settings.power_meter === "hass") return Boolean(this.settings.default_power_entity_id);
    if (this.settings.power_meter === "shelly") return Boolean(this.settings.shelly_ip);
    if (this.settings.power_meter === "kasa") return Boolean(this.settings.kasa_ip);
    return this.settings.power_meter === "dummy";
  }

  private clearPowerMeterTestResult(): void {
    this.controller.clearPowerMeterTestResult();
  }

  private discoverShellys(): void {
    void this.controller.discoverShellys();
  }

  private pendingType(): MeasureType | undefined {
    if (this.request) return this.request.measure_type;
    return this.selectedMeasureType;
  }

  private canResumeSession(): boolean {
    const type = this.snapshot?.request?.measure_type ?? this.request?.measure_type;
    return this.definitions.find((definition) => definition.measure_type === type)?.supports_resume ?? false;
  }

  /** Headline numbers, shown for whichever of them preflight was able to estimate. */
  private reviewMetrics(): ReviewMetric[] {
    if (!this.request || !this.preflight) return [];
    const { estimated_variations: variations, estimated_duration_seconds: duration } = this.preflight;
    if (variations === undefined && duration === undefined) return [];
    const metrics: ReviewMetric[] = [
      { label: "Variations", value: String(variations ?? "—") },
      { label: "Estimated time", value: duration === undefined ? "—" : this.duration(duration) },
    ];
    for (const [field, values] of this.multiSelections()) {
      metrics.push({ label: field.label, value: String(values.length) });
    }
    return metrics;
  }

  private reviewSummary(): ReviewRow[] {
    const request = this.request;
    if (!request) return [];
    const definition = this.definitionFor(request.measure_type);
    const rows: ReviewRow[] = [{ label: "Type", value: definition?.label ?? request.measure_type }];
    if (definition?.supports_profile) rows.push({ label: "Model", value: `${request.product_name} (${request.model_id})` });
    if (request.measure_device) rows.push({ label: "Device", value: request.measure_device });
    // Name the controller with the label the server gave its field — "Light", "Media player", …
    const controller = definition?.fields.find((field) => field.role === "controller");
    const entity = controller && requestFieldValue(request, controller);
    if (controller) {
      rows.push({ label: controller.label, value: typeof entity === "string" && entity ? entity : "Virtual device" });
    }
    rows.push({
      label: "Power",
      value: request.power_meter.type === "hass" ? request.power_meter.entity_id : request.power_meter.type,
    });
    for (const [field, values] of this.multiSelections()) {
      rows.push({ label: field.label, value: values.join(", ") });
    }
    const battery = this.batterySource(request);
    if (battery) rows.push({ label: "Battery", value: battery });
    if (request.dummy_load) rows.push({ label: "Dummy load", value: this.dummyLoadSummary(request.dummy_load) });
    return rows;
  }

  /** Multi-select fields of the pending request, paired with what it selected. */
  private multiSelections(): [FormField, string[]][] {
    const request = this.request;
    if (!request) return [];
    return (this.definitionFor(request.measure_type)?.fields ?? [])
      .filter((field) => field.control === "multi_select")
      .flatMap((field) => {
        const values = requestFieldValue(request, field);
        return Array.isArray(values) ? [[field, values] as [FormField, string[]]] : [];
      });
  }

  /** Where the battery level is read from, when preflight found one. */
  private batterySource(request: MeasurementRequest): string | undefined {
    if (!this.preflight) return undefined;
    if (this.preflight.battery_level_entity_id) return this.preflight.battery_level_entity_id;
    const { controller } = request as { controller?: { type: string; entity_id?: string } };
    if (!this.preflight.battery_level_attribute || controller?.type !== "hass") return undefined;
    return `${controller.entity_id} · ${this.preflight.battery_level_attribute} attribute`;
  }

  private definitionFor(type: MeasureType): MeasureDefinition | undefined {
    return this.definitions.find((definition) => definition.measure_type === type);
  }

  private reviewCanOverwrite(): boolean {
    return this.request?.resume_policy === "overwrite";
  }

  private confirmationAction(): string {
    const type = this.snapshot?.request?.measure_type ?? this.request?.measure_type;
    return this.definitions.find((definition) => definition.measure_type === type)?.confirmation_action ?? "";
  }

  private confirmationIsWarning(): boolean {
    const type = this.snapshot?.request?.measure_type ?? this.request?.measure_type;
    return this.definitions.find((definition) => definition.measure_type === type)?.confirmation_is_warning ?? false;
  }

  private duration(seconds: number): string {
    if (seconds < 60) return `${Math.ceil(seconds)} sec`;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.ceil((seconds % 3600) / 60);
    return hours ? `${hours} hr ${minutes} min` : `${minutes} min`;
  }

  private dummyLoadSummary(dummyLoad: NonNullable<MeasurementRequest["dummy_load"]>): string {
    return dummyLoad.mode === "reuse"
      ? `${dummyLoad.description} (${dummyLoad.resistance} Ω, saved calibration)`
      : `${dummyLoad.description} (calibrate before measurement)`;
  }

  private async boot(): Promise<void> {
    await this.controller.boot();
  }

  private measureTypeSelected(event: CustomEvent<MeasureType>): void {
    this.controller.selectMeasureType(event.detail);
  }
  private entityDomainsRequested(event: CustomEvent<string[]>): void {
    this.controller.loadEntityDomains(event.detail);
  }
  private runPreflight(event: CustomEvent<MeasurementRequest>): void {
    void this.controller.preflight(event.detail);
  }
  private backToSetup(): void {
    this.controller.backToSetup();
  }
  private start(): void {
    void this.controller.start();
  }
  private cancel(): void {
    void this.controller.cancel();
  }
  private confirm(): void {
    void this.controller.confirm();
  }
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
    this.controller.newMeasurement();
  }
  private resume(): void {
    void this.controller.resume();
  }
  private openSettings(event?: Event): void {
    const detail = (event as CustomEvent | undefined)?.detail;
    const section = detail && typeof detail === "object" && "section" in detail
      ? (detail as { section?: SettingsSection }).section
      : undefined;
    this.controller.openSettings(section);
  }
  private closeSettings(): void {
    this.controller.closeSettings();
  }
  private testPowerMeter(event: CustomEvent<AppSettings>): void {
    void this.controller.testPowerMeter(event.detail);
  }
  private saveSettings(event: CustomEvent<AppSettings>): void {
    void this.controller.saveSettings(event.detail);
  }
  private retryDummyLoadCalibration(): void {
    void this.controller.retryDummyLoadCalibration();
  }
  private startContributionDeviceAuth(): void {
    void this.controller.startContributionDeviceAuth();
  }
  private saveContributionToken(event: CustomEvent<string>): void {
    void this.controller.saveContributionToken(event.detail);
  }
  private disconnectContributionAuth(): void {
    void this.controller.disconnectContributionAuth();
  }
  private previewContribution(event: CustomEvent<ContributionPreviewRequest>): void {
    void this.controller.previewContribution(event.detail);
  }
  private submitContribution(event: CustomEvent<ContributionSubmitRequest>): void {
    void this.controller.submitContribution(event.detail);
  }
  private stepClass(index: number): string {
    const current = this.currentStep();
    if (index === current) return "active";
    if (index < current) return "done";
    return "";
  }
  private currentStep(): number { return { loading: 0, setup: 0, review: 1, running: 2, result: 3, settings: 0 }[this.view]; }
}

customElements.define("powercalc-measure-app", AppShell);
