import { LitElement, css, html, nothing } from "lit";
import { customElement } from "lit/decorators.js";
import { MeasureApiClient, SessionEventStream } from "../api-client";
import { MeasureAppController } from "../app-controller";
import type { AppView, MeasureAppState } from "../app-controller";

import { isAddressed, specFromRequest, specFromSettings } from "../power-meter";
import type { MeterContext } from "../power-meter";
import { reviewMetrics, reviewSummary } from "../review-summary";
import type { AppSettings, AppSettingsUpdate, Capabilities, ContributionAuthDeviceStatus, ContributionAuthState, ContributionDeviceFlow, ContributionPreview, ContributionPreviewRequest, ContributionResult, ContributionSubmitRequest, DummyLoadCalibration, EntityDescriptor, ErrorHelp, MeasureDefinition, MeasureType, MeasurementRequest, PlotCollection, PowerMeterSpec, PowerMeterDiagnostic, PreflightResponse, SessionFile, SessionSnapshot, SessionSummary, SettingsSection, ShellyDiscoveryDevice } from "../types";
import { sharedStyles } from "../styles";
import "./preflight-view";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";
import "./sessions-view";

const POWERCALC_LOGO_URL = new URL("../assets/powercalc-logo.svg", import.meta.url).href;

/**
 * The measurement flow, in order. The progress bar belongs to a session being configured or run,
 * so it is shown for these views only — never while loading, in the session overview, or in settings.
 */
const MEASUREMENT_STEPS: readonly { view: AppView; label: string }[] = [
  { view: "setup", label: "Set up" },
  { view: "review", label: "Review" },
  { view: "running", label: "Measure" },
  { view: "result", label: "Result" },
];

/**
 * Root element. It owns the application state as plain fields — the controller mutates them and
 * asks for a re-render, so none of it needs Lit's reactive property machinery.
 */
@customElement("powercalc-measure-app")
export class AppShell extends LitElement implements MeasureAppState {
  view: AppView = "loading";
  settingsSection?: SettingsSection;
  loadingMessage = "Connecting to Home Assistant…";
  errorMessage = "";
  errorHelp?: ErrorHelp;
  busy = false;
  lastAnalysedSessionId?: string;
  connectedToEvents = false;
  snapshot?: SessionSnapshot;
  sessions: SessionSummary[] = [];
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
  measureDevices: string[] = [];
  measureDevicesLoading = false;
  measureDevicesError = "";
  contributionAuth?: ContributionAuthState;
  contributionDeviceFlow?: ContributionDeviceFlow;
  contributionDeviceStatus?: ContributionAuthDeviceStatus;
  contributionDraft?: ContributionPreview;
  contributionPreview?: ContributionPreview;
  contributionResult?: ContributionResult;
  contributionBusy = false;
  contributionAuthBusy = false;
  contributionError = "";
  contributionErrorField?: string;
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

  private readonly api: MeasureApiClient = new MeasureApiClient();
  private readonly controller = new MeasureAppController(
    this,
    () => this.api,
    (sessionId, { onEvent, onConnection, onReconnect }) => new SessionEventStream(this.api.eventsUrl(sessionId), onEvent, onConnection, onReconnect),
    () => this.requestUpdate(),
  );

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-height: 100vh; background: var(--canvas); }
    .shell { width: min(1320px, calc(100% - 2rem)); margin: 0 auto; padding: clamp(1rem, 3vw, 2rem) 0 4rem; }
    header { margin-bottom: clamp(1.5rem, 4vw, 2.5rem); }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--line); }
    .brand { display: flex; align-items: center; gap: 0.7rem; min-height: 36px; padding: 0; border: 0; background: transparent; color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.16em; text-transform: uppercase; }
    .brand:hover:not(:disabled) { border-color: transparent; background: transparent; color: var(--ink); transform: none; }
    .brand:active:not(:disabled) { transform: none; }
    .brand-logo { width: 20px; height: 24px; object-fit: contain; }
    .version { color: var(--muted); font: 500 0.68rem/1 ui-monospace, monospace; letter-spacing: normal; text-transform: none; white-space: nowrap; }
    .intro { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.78fr); gap: 1.25rem clamp(1.5rem, 5vw, 4rem); align-items: end; padding-top: clamp(1.5rem, 4vw, 2.5rem); }
    h1 { grid-column: 1 / -1; margin: 0; font-size: clamp(2rem, 3.4vw, 3rem); line-height: 1; letter-spacing: -0.04em; }
    .subtitle { max-width: 540px; margin: 0.8rem 0 0; color: var(--muted); font-size: 1rem; line-height: 1.6; }
    .topbar-actions { display: flex; align-items: center; gap: 0.55rem; }
    .topbar-action { min-height: 36px; padding: 0.4rem 0.8rem; border-radius: 999px; font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.08em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 0.45rem; }
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
    footer { margin-top: 1rem; color: var(--muted); font-size: 0.72rem; text-align: right; }
    @media (max-width: 700px) { .intro { grid-template-columns: 1fr; } h1 { grid-column: auto; } .sequence { max-width: 560px; } .calibration-warning { align-items: flex-start; flex-direction: column; } }
    @media (max-width: 460px) { .shell { width: min(100% - 1.25rem, 980px); } .brand .version { display: none; } .topbar-action { padding-inline: 0.65rem; font-size: 0.66rem; } .sequence { gap: 0.3rem; } .sequence > li { font-size: 0.58rem; letter-spacing: 0.04em; } .sequence > li:not(:last-child)::after { left: calc(20px + 0.3rem); width: calc(100% - 40px - 0.3rem); } }
  `];

  connectedCallback(): void { super.connectedCallback(); void this.boot(); }
  disconnectedCallback(): void { this.controller.dispose(); super.disconnectedCallback(); }

  render() {
    return html`
      <main class="shell">
        <header>
          <div class="topbar">
            <button class="brand" type="button" aria-label="Open all measurement sessions" @click=${this.showSessions} ?disabled=${this.view === "loading"}>
              <img class="brand-logo" src=${POWERCALC_LOGO_URL} alt="" />
              <span>Powercalc Measure</span>
              ${this.capabilities?.runtime_version
                ? html`<span class="version">Version ${this.displayVersion()}</span>`
                : nothing}
            </button>
            <div class="topbar-actions">
              <button class="topbar-action sessions-toggle" type="button" @click=${this.showSessions} ?disabled=${this.view === "loading" || this.view === "sessions"}>All sessions</button>
              <button class="topbar-action settings-toggle" type="button" @click=${this.openSettings} ?disabled=${this.view === "loading" || this.view === "settings"}>Settings</button>
            </div>
          </div>
          <div class="intro">
            <h1>Turn real watts into a precise profile.</h1>
            <div>
            <p class="subtitle">Configure, validate, and monitor a power measurement without leaving Home Assistant.</p>
            </div>
            ${this.renderProgress()}
          </div>
        </header>
        ${this.dummyLoadCalibrationError ? html`
          <div class="notice calibration-warning" role="status">
            <span>${this.dummyLoadCalibrationError}</span>
            <button type="button" @click=${() => void this.controller.retryDummyLoadCalibration()}>Retry</button>
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
    switch (this.view) {
      case "loading": return this.renderLoading();
      case "settings": return this.renderSettings();
      case "sessions": return this.renderSessions();
      case "review": return this.preflight && this.request ? this.renderReview() : this.renderSetup();
      case "running": return this.snapshot ? this.renderRunning(this.snapshot) : this.renderSetup();
      case "result": return this.snapshot ? this.renderResult(this.snapshot) : this.renderSetup();
      default: return this.renderSetup();
    }
  }

  private renderSettings() {
    return html`
      <measure-settings-view
        .powers=${this.powers} .settings=${this.settings} .capabilities=${this.capabilities}
        .measureDevices=${this.measureDevices} .measureDevicesLoading=${this.measureDevicesLoading} .measureDevicesError=${this.measureDevicesError}
        .busy=${this.busy} .testing=${this.testingPowerMeter} .testResult=${this.powerMeterTestResult} .errorMessage=${this.errorMessage}
        .shellyDiscoveryDevices=${this.shellyDiscoveryDevices} .discoveringShellys=${this.discoveringShellys}
        .shellyDiscoveryError=${this.shellyDiscoveryError} .shellyDiscoveryAvailable=${this.shellyDiscoveryAvailable}
        .shellyDiscoveryMessage=${this.shellyDiscoveryMessage}
        .contributionAuth=${this.contributionAuth} .contributionDeviceFlow=${this.contributionDeviceFlow}
        .contributionDeviceStatus=${this.contributionDeviceStatus} .contributionAuthBusy=${this.contributionAuthBusy}
        .contributionAuthError=${this.contributionAuthError} .initialSection=${this.settingsSection}
        @back=${() => this.controller.closeSettings()} @save=${(event: CustomEvent<AppSettingsUpdate>) => void this.controller.saveSettings(event.detail)}
        @test=${(event: CustomEvent<AppSettingsUpdate>) => void this.controller.testPowerMeter(event.detail)} @test-clear=${() => this.controller.clearPowerMeterTestResult()}
        @shelly-discover=${() => void this.controller.discoverShellys()} @github-device-start=${() => void this.controller.startContributionDeviceAuth()}
        @github-token-save=${(event: CustomEvent<string>) => void this.controller.saveContributionToken(event.detail)}
        @github-disconnect=${() => void this.controller.disconnectContributionAuth()}
      ></measure-settings-view>`;
  }

  private renderSessions() {
    return html`
      <measure-sessions-view
        .sessions=${this.sessions} .busy=${this.busy} .errorMessage=${this.errorMessage}
        .diagnosticsUrl=${(sessionId: string) => this.api.diagnosticsUrl(sessionId)}
        @new=${() => this.controller.newMeasurement()} @open=${(event: CustomEvent<string>) => void this.controller.openSession(event.detail)}
        @resume=${(event: CustomEvent<string>) => void this.controller.resumeSession(event.detail)}
        @duplicate=${(event: CustomEvent<string>) => void this.controller.duplicateSession(event.detail)}
        @delete=${(event: CustomEvent<string>) => void this.controller.deleteSession(event.detail)}
      ></measure-sessions-view>`;
  }

  private renderReview() {
    const definition = this.activeDefinition();
    return html`
      <measure-preflight-view
        .metrics=${reviewMetrics(this.request, this.preflight, definition)}
        .summary=${reviewSummary(this.request, this.preflight, definition)}
        .warnings=${this.preflight?.warnings ?? []} .powerMeterDiagnostic=${this.preflight?.power_meter_diagnostic}
        .lightLoadProbe=${this.preflight?.light_load_probe}
        .confirmationAction=${this.confirmationAction()}
        .busy=${this.busy} .errorMessage=${this.errorMessage} .errorHelp=${this.errorHelp}
        @back=${() => this.controller.backToSetup()} @start=${() => void this.controller.start()}
      ></measure-preflight-view>`;
  }

  private renderRunning(snapshot: SessionSnapshot) {
    return html`
      <measure-running-view
        .snapshot=${snapshot} .confirmationAction=${this.confirmationAction()} .warningConfirmation=${this.confirmationIsWarning()}
        .connected=${this.connectedToEvents} .logs=${this.logs} .samples=${this.samples}
        .diagnosticsUrl=${this.api.diagnosticsUrl(snapshot.session_id ?? "")} .busy=${this.busy}
        @cancel=${() => void this.controller.cancel()} @confirm=${() => void this.controller.confirm()}
      ></measure-running-view>`;
  }

  private renderResult(snapshot: SessionSnapshot) {
    const sessionId = snapshot.session_id ?? "";
    return html`
      <measure-result-view
        .snapshot=${snapshot} .files=${this.files} .plotCollection=${this.plotCollection}
        .fileUrl=${(name: string) => this.api.fileUrl(sessionId, name)} .downloadAll=${this.downloadAllFiles.bind(this)}
        .inspectJsonFile=${(name: string) => this.api.getJsonFile(sessionId, name)}
        .diagnosticsUrl=${this.api.diagnosticsUrl(sessionId)}
        .busy=${this.busy} .canResume=${this.canResumeSession()} .canAnalyse=${Boolean(snapshot.can_analyse)}
        .analysisComplete=${this.lastAnalysedSessionId === sessionId}
        .errorMessage=${this.errorMessage} .errorHelp=${this.errorHelp}
        .contributionAuth=${this.contributionAuth} .contributionDraft=${this.contributionDraft}
        .contributionPreview=${this.contributionPreview} .contributionResult=${this.contributionResult}
        .contributionBusy=${this.contributionBusy} .contributionError=${this.contributionError}
        .contributionErrorField=${this.contributionErrorField}
        @sessions=${this.showSessions} @new=${() => this.controller.newMeasurement()} @resume=${() => void this.controller.resume()}
        @analyse=${() => void this.controller.analyseRecording()}
        @open-settings=${this.openSettings}
        @contribution-preview=${(event: CustomEvent<ContributionPreviewRequest>) => void this.controller.previewContribution(event.detail)}
        @contribution-submit=${(event: CustomEvent<ContributionSubmitRequest>) => void this.controller.submitContribution(event.detail)}
      ></measure-result-view>`;
  }

  private renderSetup() {
    return html`
      <measure-setup-view
        .capabilities=${this.capabilities} .definitions=${this.definitions}
        .lights=${this.lights} .powers=${this.powers} .voltages=${this.voltages}
        .deviceEntities=${this.deviceEntities} .deviceEntityErrors=${this.deviceEntityErrors}
        .initialType=${this.pendingType()} .initialRequest=${this.request}
        .dummyLoadCalibration=${this.dummyLoadCalibration}
        .meter=${this.meterSpec()}
        .defaultMeasureDevice=${this.request?.measure_device ?? this.settings?.default_measure_device ?? ""}
        .powerMeterConfigured=${this.powerMeterConfigured()}
        .busy=${this.busy} .errorMessage=${this.errorMessage} .errorHelp=${this.errorHelp}
        @preflight=${(event: CustomEvent<MeasurementRequest>) => void this.controller.preflight(event.detail)}
        @measure-type-selected=${(event: CustomEvent<MeasureType>) => this.controller.selectMeasureType(event.detail)}
        @entity-domains-requested=${(event: CustomEvent<string[]>) => this.controller.loadEntityDomains(event.detail)}
        @use-current-settings=${this.useCurrentSettings}
        @open-settings=${this.openSettings}
      ></measure-setup-view>`;
  }

  /** The meter the setup form should start from: the draft's own, else the saved default. */
  private meterSpec(): PowerMeterSpec {
    return specFromRequest(this.request, this.settings, this.meterContext());
  }

  private meterContext(): MeterContext {
    return { powers: this.powers, voltages: this.voltages };
  }

  private powerMeterConfigured(): boolean {
    const device = this.request ? this.request.measure_device : this.settings?.default_measure_device;
    if (!device) return false;
    if (!this.request && !this.settings?.power_meter) return false;
    return isAddressed(this.meterSpec());
  }

  /** Drop the session's stored environment and continue from the app defaults instead. */
  private useCurrentSettings(): void {
    const settings = this.settings;
    if (!settings) return;
    const spec = specFromSettings(settings, this.meterContext());
    this.controller.replaceDraftEnvironment(spec, settings.default_measure_device ?? "");
  }

  private pendingType(): MeasureType | undefined {
    if (this.request) return this.request.measure_type;
    return this.selectedMeasureType;
  }

  private canResumeSession(): boolean {
    const retained = this.sessions.find((session) => session.session_id === this.snapshot?.session_id);
    if (retained) return retained.can_resume;
    return this.activeDefinition()?.supports_resume ?? false;
  }

  /** The definition of the type being measured or configured, whichever the current view is about. */
  private activeDefinition(): MeasureDefinition | undefined {
    const type = this.snapshot?.request?.measure_type ?? this.request?.measure_type;
    return this.definitions.find((definition) => definition.measure_type === type);
  }

  private confirmationAction(): string {
    const request = this.snapshot?.request ?? this.request;
    return this.snapshot?.confirmation_action
      ?? this.activeDefinition()?.confirmation_action
      ?? (request?.dummy_load ? "Start measurement" : "");
  }

  private confirmationIsWarning(): boolean {
    return this.activeDefinition()?.confirmation_is_warning ?? false;
  }

  /** Load everything the app needs to show a first screen. Also the seam the tests stub out. */
  private async boot(): Promise<void> {
    await this.controller.boot();
  }

  private downloadAllFiles(): void {
    const sessionId = this.snapshot?.session_id;
    if (!sessionId) return;
    for (const file of this.files) {
      const anchor = document.createElement("a");
      anchor.href = this.api.fileUrl(sessionId, file.name);
      anchor.download = file.name.split("/").pop() ?? file.name;
      anchor.rel = "noopener";
      anchor.style.display = "none";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
    }
  }

  private showSessions(): void {
    void this.controller.showSessions();
  }

  /** Settings can be opened bare from the top bar, or aimed at a section by a view that links into it. */
  private openSettings(event?: Event): void {
    const detail = (event as CustomEvent | undefined)?.detail;
    const section = detail && typeof detail === "object" && "section" in detail
      ? (detail as { section?: SettingsSection }).section
      : undefined;
    this.controller.openSettings(section);
  }

  private renderProgress() {
    const current = this.currentStep();
    if (current < 0) return nothing;
    return html`
      <nav aria-label="Measurement progress">
        <ol class="sequence">
          ${MEASUREMENT_STEPS.map(({ label }, index) => html`
            <li class=${stepClass(index, current)} aria-current=${index === current ? "step" : nothing}>
              <span class="step-number">${index < current ? "✓" : index + 1}</span><span>${label}</span>
            </li>`)}
        </ol>
      </nav>`;
  }

  /** Index within the measurement flow, or -1 for a view outside it. */
  private currentStep(): number {
    return MEASUREMENT_STEPS.findIndex((step) => step.view === this.view);
  }
}

function stepClass(index: number, current: number): string {
  if (index === current) return "active";
  if (index < current) return "done";
  return "";
}
