import { ApiError } from "./api-client";
import type { MeasureApiClient } from "./api-client";
import { entityDomains, requestFormData } from "./measure-definition";
import { meterFor } from "./power-meter";
import { emptyPlots } from "./types";
import type {
  AppSettings,
  AppSettingsUpdate,
  Capabilities,
  ContributionAuthDeviceStatus,
  ContributionAuthState,
  ContributionDeviceFlow,
  ContributionFormValues,
  ContributionPreview,
  ContributionPreviewRequest,
  ContributionResult,
  ContributionStatus,
  ContributionSubmitRequest,
  DummyLoadCalibration,
  DeviceSpecificationField,
  EntityDescriptor,
  ErrorHelp,
  MeasureDefinition,
  MeasureType,
  MeasurementRequest,
  PlotCollection,
  PowerMeterDiagnostic,
  PreflightResponse,
  SessionEvent,
  SessionFile,
  SessionSnapshot,
  SessionState,
  SessionSummary,
  SettingsSection,
  ShellyDiscoveryDevice,
} from "./types";

export type AppView = "loading" | "sessions" | "setup" | "review" | "running" | "result" | "profile" | "share" | "settings";

export interface MeasureAppState {
  view: AppView;
  settingsSection?: SettingsSection;
  errorMessage: string;
  errorHelp?: ErrorHelp;
  busy: boolean;
  connectedToEvents: boolean;
  snapshot?: SessionSnapshot;
  sessions: SessionSummary[];
  request?: MeasurementRequest;
  selectedMeasureType?: MeasureType;
  preflight?: PreflightResponse;
  files: SessionFile[];
  plotCollection: PlotCollection;
  logs: string[];
  samples: number[];
  capabilities?: Capabilities;
  lights: EntityDescriptor[];
  powers: EntityDescriptor[];
  voltages: EntityDescriptor[];
  dummyLoadCalibration: DummyLoadCalibration | null;
  dummyLoadCalibrationError: string;
  settings?: AppSettings;
  measureDevices: string[];
  measureDevicesLoading: boolean;
  measureDevicesError: string;
  manufacturers?: string[];
  deviceSpecificationFields: Record<string, DeviceSpecificationField[]>;
  contributionAuth?: ContributionAuthState;
  contributionDeviceFlow?: ContributionDeviceFlow;
  contributionDeviceStatus?: ContributionAuthDeviceStatus;
  contributionDraft?: ContributionPreview;
  contributionFormValues?: ContributionFormValues;
  contributionPreview?: ContributionPreview;
  contributionResult?: ContributionResult;
  contributionBusy: boolean;
  contributionAuthBusy: boolean;
  contributionError: string;
  contributionErrorField?: string;
  contributionAuthError: string;
  definitions: MeasureDefinition[];
  deviceEntities: Record<string, EntityDescriptor[]>;
  deviceEntityErrors: Record<string, string>;
  testingPowerMeter: boolean;
  powerMeterTestResult?: PowerMeterDiagnostic;
  shellyDiscoveryDevices: ShellyDiscoveryDevice[];
  discoveringShellys: boolean;
  shellyDiscoveryError: string;
  shellyDiscoveryAvailable?: boolean;
  shellyDiscoveryMessage?: string | null;
}

/**
 * Everything the controller calls on the API client. Derived from the client itself so the two
 * cannot drift; the URL builders are excluded because only the shell hands those to its views.
 */
export type MeasureAppApi = Omit<
  MeasureApiClient,
  "fileUrl" | "diagnosticsUrl" | "eventsUrl" | "preparedProfileUrl"
>;

export interface EventConnection {
  connect(): void;
  close(): void;
}

interface EventCallbacks {
  onEvent: (event: SessionEvent) => void;
  onConnection: (connected: boolean) => void;
  onReconnect: () => void;
}

type EventConnectionFactory = (sessionId: string, callbacks: EventCallbacks) => EventConnection;

/** Framework-neutral application controller. Lit only observes the state mutations. */
export class MeasureAppController {
  private eventConnection?: EventConnection;
  private settingsReturnView: AppView = "setup";
  private powerMeterTestVersion = 0;
  private shellyDiscoveryVersion = 0;
  private contributionDeviceFlowVersion = 0;
  private contributionDevicePollInterval = 0;
  private contributionDeviceExpiresAt = 0;
  private contributionDevicePollTimer?: ReturnType<typeof setTimeout>;
  private readonly contributionTouchedFields = new Set<string>();

  constructor(
    private readonly state: MeasureAppState,
    private readonly api: () => MeasureAppApi,
    private readonly createEventConnection: EventConnectionFactory,
    private readonly changed: () => void,
  ) {}

  private clearError(): void {
    this.state.errorMessage = "";
    this.state.errorHelp = undefined;
  }

  private setError(error: unknown): void {
    this.state.errorMessage = message(error);
    this.state.errorHelp = error instanceof ApiError ? error.help : undefined;
  }

  dispose(): void {
    this.shellyDiscoveryVersion += 1;
    this.stopContributionDevicePolling();
    this.state.contributionAuthBusy = false;
    this.eventConnection?.close();
  }

  async boot(): Promise<void> {
    this.state.view = "loading";
    this.clearError();
    this.changed();
    try {
      const api = this.api();
      const calibrationPromise = this.refreshDummyLoadCalibration();
      const [capabilities, entities, settings, auth, sessions, definitions] = await Promise.all([
        api.getCapabilities(),
        api.getEntityCatalog(),
        api.getSettings(),
        api.getContributionAuth().catch(() => ({ connected: false }) satisfies ContributionAuthState),
        api.getSessions(),
        api.getMeasureDefinitions(),
      ]);
      this.state.capabilities = capabilities;
      this.state.lights = entities.lights;
      this.state.powers = entities.powers;
      this.state.voltages = entities.voltages;
      this.state.settings = settings;
      this.state.contributionAuth = auth;
      this.state.sessions = sessions;
      const active = sessions.find((session) => session.active);
      this.state.snapshot = active ? await api.getSession(active.session_id) : undefined;
      this.state.definitions = definitions;
      await calibrationPromise;
      this.state.request = this.state.snapshot?.request;
      if (this.state.request) await this.loadTypeEntities(this.state.request.measure_type);
      await this.routeSnapshot();
    } catch (error) {
      this.setError(error);
    }
    this.changed();
  }

  selectMeasureType(type: MeasureType): void {
    this.state.selectedMeasureType = type;
    this.changed();
    void this.loadTypeEntities(type);
  }

  loadEntityDomains(domains: string[]): void {
    void this.ensureEntityDomains(domains);
  }

  async preflight(request: MeasurementRequest): Promise<void> {
    this.state.request = request;
    await this.run(async () => {
      this.state.preflight = await this.api().preflight(request);
      this.state.view = "review";
    });
  }

  backToSetup(): void {
    this.clearError();
    this.state.view = "setup";
    this.changed();
  }

  async start(): Promise<void> {
    const request = this.state.request;
    if (!request) return;
    this.state.samples = [];
    this.state.plotCollection = emptyPlots();
    await this.run(async () => {
      this.state.snapshot = await this.api().start(request);
      await this.enterRunning();
    });
  }

  async confirm(): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    await this.sessionCommand("Confirmation", () => this.api().confirm(sessionId));
  }

  async cancel(): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    await this.sessionCommand("Cancellation", () => this.api().cancel(sessionId));
  }

  async resume(): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    this.state.plotCollection = emptyPlots();
    await this.run(async () => {
      this.state.snapshot = await this.api().resume(sessionId);
      await this.enterRunning();
    });
  }

  newMeasurement(): void {
    this.resetDraft();
    this.state.view = "setup";
    this.changed();
  }

  openProfile(): void {
    if (this.state.snapshot?.state !== "completed" || this.isAverageMeasurement()) return;
    this.clearError();
    this.state.view = "profile";
    this.changed();
  }

  openShare(): void {
    if (this.state.snapshot?.state !== "completed" || !this.state.contributionPreview || this.isAverageMeasurement()) return;
    if (Object.keys(this.state.contributionFormValues ?? {}).length) return;
    this.clearError();
    this.state.view = "share";
    this.changed();
  }

  backToProfile(): void {
    if (this.isAverageMeasurement()) return;
    this.clearError();
    this.state.view = "profile";
    this.changed();
  }

  private isAverageMeasurement(): boolean {
    return (this.state.snapshot?.request?.measure_type ?? this.state.request?.measure_type ?? this.state.selectedMeasureType) === "average";
  }

  backToResult(): void {
    this.clearError();
    this.state.view = "result";
    this.changed();
  }

  replaceDraftEnvironment(powerMeter: MeasurementRequest["power_meter"], measureDevice: string): void {
    if (!this.state.request) return;
    this.state.request = { ...this.state.request, power_meter: powerMeter, measure_device: measureDevice };
    this.changed();
  }

  async showSessions(): Promise<void> {
    this.eventConnection?.close();
    this.state.connectedToEvents = false;
    await this.run(async () => {
      await this.refreshSessions();
      this.state.view = "sessions";
    });
  }

  async openSession(sessionId: string): Promise<void> {
    await this.run(async () => {
      const snapshot = await this.api().getSession(sessionId);
      this.state.snapshot = snapshot;
      await this.adoptRequest(snapshot.request);
      if (isActive(snapshot.state)) {
        this.state.view = "running";
        this.connectEvents();
      } else {
        await this.enterResult();
      }
    });
  }

  async resumeSession(sessionId: string): Promise<void> {
    this.state.plotCollection = emptyPlots();
    await this.run(async () => {
      const snapshot = await this.api().resume(sessionId);
      this.state.snapshot = snapshot;
      await this.adoptRequest(snapshot.request);
      await this.enterRunning();
    });
  }

  async duplicateSession(sessionId: string): Promise<void> {
    await this.run(async () => {
      const snapshot = await this.api().getSession(sessionId);
      if (!snapshot.request) throw new Error("The stored session has no reusable configuration.");
      const draft = { ...snapshot.request, resume_policy: "new" as const };
      this.resetDraft(draft);
      await this.loadTypeEntities(draft.measure_type, draft);
      this.state.view = "setup";
    });
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.run(async () => {
      await this.api().deleteSession(sessionId);
      if (this.state.snapshot?.session_id === sessionId) this.state.snapshot = undefined;
      await this.refreshSessions();
    });
  }

  openSettings(section?: SettingsSection): void {
    if (this.state.view === "loading" || this.state.view === "settings") return;
    this.settingsReturnView = this.state.view;
    this.state.settingsSection = section;
    this.clearError();
    this.powerMeterTestVersion += 1;
    this.state.powerMeterTestResult = undefined;
    this.state.testingPowerMeter = false;
    this.state.view = "settings";
    this.changed();
    void this.loadMeasureDevices();
    const meter = this.state.settings?.power_meter;
    if (meter && meterFor(meter).discoverable) void this.discoverShellys();
  }

  closeSettings(): void {
    this.clearError();
    this.state.view = this.settingsReturnView;
    this.changed();
  }

  private async loadMeasureDevices(): Promise<void> {
    this.state.measureDevicesLoading = true;
    this.state.measureDevicesError = "";
    this.changed();
    try {
      this.state.measureDevices = (await this.api().getMeasureDevices()).devices;
    } catch (error) {
      this.state.measureDevicesError = message(error);
    } finally {
      this.state.measureDevicesLoading = false;
      this.changed();
    }
  }

  async testPowerMeter(settings: AppSettingsUpdate): Promise<void> {
    const version = ++this.powerMeterTestVersion;
    this.state.testingPowerMeter = true;
    this.state.powerMeterTestResult = undefined;
    this.changed();
    try {
      const result = await this.api().testPowerMeter(settings);
      if (version === this.powerMeterTestVersion) this.state.powerMeterTestResult = result;
    } catch (error) {
      if (version === this.powerMeterTestVersion) {
        this.state.powerMeterTestResult = {
          success: false,
          status: "poor",
          reports_observed: 0,
          duration_seconds: 0,
          precision_status: "unsupported",
          update_interval_status: "unsupported",
          messages: [],
          message: message(error),
        };
      }
    } finally {
      if (version === this.powerMeterTestVersion) {
        this.state.testingPowerMeter = false;
        this.changed();
      }
    }
  }

  clearPowerMeterTestResult(): void {
    this.powerMeterTestVersion += 1;
    this.state.testingPowerMeter = false;
    this.state.powerMeterTestResult = undefined;
    this.changed();
  }

  async discoverShellys(): Promise<void> {
    const version = ++this.shellyDiscoveryVersion;
    this.state.discoveringShellys = true;
    this.state.shellyDiscoveryError = "";
    this.changed();
    try {
      const result = await this.api().getShellyDevices();
      if (version !== this.shellyDiscoveryVersion) return;
      this.state.shellyDiscoveryDevices = result.devices;
      this.state.shellyDiscoveryAvailable = result.available;
      this.state.shellyDiscoveryMessage = result.message;
    } catch (error) {
      if (version !== this.shellyDiscoveryVersion) return;
      this.state.shellyDiscoveryError = message(error);
    } finally {
      if (version === this.shellyDiscoveryVersion) {
        this.state.discoveringShellys = false;
        this.changed();
      }
    }
  }

  async saveSettings(settings: AppSettingsUpdate): Promise<void> {
    await this.run(async () => {
      this.state.settings = await this.api().saveSettings(settings);
      [this.state.capabilities] = await Promise.all([
        this.api().getCapabilities(),
        this.refreshDummyLoadCalibration(),
        this.refreshContributionDefaults(),
      ]);
      this.state.view = this.settingsReturnView;
    });
  }

  private async refreshContributionDefaults(): Promise<void> {
    const previous = this.state.contributionDraft;
    const sessionId = this.state.snapshot?.session_id;
    if (!previous || !sessionId) return;
    const defaults = await this.api().getContributionDraft(sessionId);
    if (this.state.snapshot?.session_id !== sessionId) return;
    const current = this.state.contributionPreview ?? previous;
    const merged = { ...current };
    let changed = false;
    for (const field of ["contributor", "contributor_github", "contributor_email", "measure_device_firmware"] as const) {
      // Keep both edits made here (including explicit blanks) and overrides in a restored preview.
      if ((current[field] ?? "") !== (previous[field] ?? "")) this.contributionTouchedFields.add(field);
      if (this.contributionTouchedFields.has(field)) continue;
      if ((current[field] ?? "") === (defaults[field] ?? "")) continue;
      merged[field] = defaults[field] ?? "";
      changed = true;
    }
    if (changed) {
      this.state.contributionDraft = merged;
      this.state.contributionPreview = undefined;
      this.state.contributionResult = undefined;
      this.state.contributionError = "";
      this.state.contributionErrorField = undefined;
      if (this.settingsReturnView === "share") this.settingsReturnView = "profile";
    }
  }

  editContribution(values: ContributionFormValues): void {
    this.state.contributionFormValues = values;
    for (const field of Object.keys(values)) this.contributionTouchedFields.add(field);
    this.changed();
  }

  async startContributionDeviceAuth(): Promise<void> {
    this.stopContributionDevicePolling();
    const version = this.contributionDeviceFlowVersion;
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.state.contributionDeviceFlow = undefined;
    this.state.contributionDeviceStatus = undefined;
    this.changed();
    try {
      const flow = await this.api().startContributionDeviceAuth();
      if (version !== this.contributionDeviceFlowVersion) return;
      this.state.contributionDeviceFlow = flow;
      this.state.contributionDeviceStatus = {
        status: "pending",
        message: "Waiting for GitHub authorization…",
      };
      this.contributionDevicePollInterval = Math.max(1, flow.interval);
      this.contributionDeviceExpiresAt = Date.now() + Math.max(0, flow.expires_in) * 1_000;
      this.scheduleContributionDevicePoll(version);
    } catch (error) {
      if (version !== this.contributionDeviceFlowVersion) return;
      this.state.contributionAuthError = message(error);
    } finally {
      if (version === this.contributionDeviceFlowVersion) {
        this.state.contributionAuthBusy = false;
        this.changed();
      }
    }
  }

  private async pollContributionDeviceAuth(version: number): Promise<void> {
    const flowId = this.state.contributionDeviceFlow?.flow_id;
    if (!flowId || version !== this.contributionDeviceFlowVersion) return;
    if (Date.now() >= this.contributionDeviceExpiresAt) {
      this.expireContributionDeviceFlow();
      return;
    }
    try {
      const status = await this.api().getContributionDeviceAuth(flowId);
      if (this.isStaleContributionDevicePoll(version, flowId)) return;
      this.applyContributionDeviceStatus(status, version);
    } catch (error) {
      if (this.isStaleContributionDevicePoll(version, flowId)) return;
      this.handleContributionDevicePollError(error, version);
    } finally {
      if (version === this.contributionDeviceFlowVersion) this.changed();
    }
  }

  /** A poll result is stale when the flow was restarted or replaced while the request was in flight. */
  private isStaleContributionDevicePoll(version: number, flowId: string): boolean {
    return version !== this.contributionDeviceFlowVersion || flowId !== this.state.contributionDeviceFlow?.flow_id;
  }

  private applyContributionDeviceStatus(status: ContributionAuthDeviceStatus, version: number): void {
    this.state.contributionDeviceStatus = status;
    if (status.auth) this.state.contributionAuth = status.auth;
    this.state.contributionAuthError = "";

    if (status.status === "authorized") {
      this.state.contributionDeviceFlow = undefined;
      this.stopContributionDevicePolling();
      this.changed();
      return;
    }

    if (status.status !== "pending" && status.status !== "slow_down") return;

    if (status.status === "slow_down") {
      this.contributionDevicePollInterval = validRetryAfter(status.retry_after)
        ? Math.max(this.contributionDevicePollInterval, status.retry_after)
        : this.contributionDevicePollInterval + 5;
    }
    this.scheduleContributionDevicePoll(version);
  }

  private handleContributionDevicePollError(error: unknown, version: number): void {
    if (error instanceof ApiError && error.status === 404) {
      this.expireContributionDeviceFlow();
      return;
    }
    this.state.contributionAuthError = message(error);
    this.scheduleContributionDevicePoll(version);
  }

  private scheduleContributionDevicePoll(version: number): void {
    this.clearContributionDevicePollTimer();
    if (version !== this.contributionDeviceFlowVersion || !this.state.contributionDeviceFlow) return;
    const remaining = this.contributionDeviceExpiresAt - Date.now();
    if (remaining <= 0) {
      this.expireContributionDeviceFlow();
      return;
    }
    const delay = Math.min(this.contributionDevicePollInterval * 1_000, remaining);
    this.contributionDevicePollTimer = setTimeout(() => {
      this.contributionDevicePollTimer = undefined;
      void this.pollContributionDeviceAuth(version);
    }, delay);
  }

  private expireContributionDeviceFlow(): void {
    this.clearContributionDevicePollTimer();
    this.state.contributionDeviceStatus = {
      status: "expired",
      message: "This GitHub code expired. Request a new code to continue.",
    };
    this.changed();
  }

  private stopContributionDevicePolling(): void {
    this.contributionDeviceFlowVersion += 1;
    this.clearContributionDevicePollTimer();
  }

  private clearContributionDevicePollTimer(): void {
    if (this.contributionDevicePollTimer === undefined) return;
    clearTimeout(this.contributionDevicePollTimer);
    this.contributionDevicePollTimer = undefined;
  }

  async saveContributionToken(token: string): Promise<void> {
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.changed();
    try {
      this.state.contributionAuth = await this.api().saveContributionToken(token);
      this.stopContributionDevicePolling();
      this.state.contributionDeviceFlow = undefined;
      this.state.contributionDeviceStatus = undefined;
    } catch (error) {
      this.state.contributionAuthError = message(error);
    } finally {
      this.state.contributionAuthBusy = false;
      this.changed();
    }
  }

  async disconnectContributionAuth(): Promise<void> {
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.changed();
    try {
      this.state.contributionAuth = await this.api().disconnectContributionAuth();
      this.stopContributionDevicePolling();
      this.state.contributionDeviceFlow = undefined;
      this.state.contributionDeviceStatus = undefined;
    } catch (error) {
      this.state.contributionAuthError = message(error);
    } finally {
      this.state.contributionAuthBusy = false;
      this.changed();
    }
  }

  async previewContribution(request: ContributionPreviewRequest): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    await this.runContribution(async () => {
      this.state.contributionPreview = await this.api().previewContribution(sessionId, request);
      this.state.contributionFormValues = undefined;
      this.state.contributionResult = undefined;
    });
  }

  async submitContribution(request: ContributionSubmitRequest): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    await this.runContribution(async () => {
      this.state.contributionResult = await this.api().submitContribution(sessionId, request);
    });
  }

  async retryDummyLoadCalibration(): Promise<void> {
    await this.refreshDummyLoadCalibration();
    this.changed();
  }

  private async refreshDummyLoadCalibration(): Promise<void> {
    try {
      this.state.dummyLoadCalibration = await this.api().getDummyLoadCalibration();
      this.state.dummyLoadCalibrationError = "";
    } catch (error) {
      this.state.dummyLoadCalibrationError = `Could not load the saved dummy-load calibration: ${message(error)}`;
    }
  }

  private async loadTypeEntities(type: MeasureType, request?: MeasurementRequest): Promise<void> {
    const definition = this.state.definitions.find((candidate) => candidate.measure_type === type);
    if (!definition) return;
    // A restored request may make fields visible that the type's defaults do not.
    const values = request ? requestFormData(definition, request) : undefined;
    await this.ensureEntityDomains(entityDomains(definition, values));
  }

  private async ensureEntityDomains(domains: string[]): Promise<void> {
    const pending = [...new Set(domains)].filter((domain) => !(domain in this.state.deviceEntities));
    if (!pending.length) return;
    const results = await Promise.allSettled(
      pending.map((domain) => domain === "*" ? this.api().getAllEntities() : this.api().getEntitiesByDomain(domain)),
    );
    results.forEach((result, index) => {
      const domain = pending[index];
      if (!domain) return;
      if (result.status === "fulfilled") {
        this.state.deviceEntities = { ...this.state.deviceEntities, [domain]: result.value };
        const { [domain]: _, ...remainingErrors } = this.state.deviceEntityErrors;
        this.state.deviceEntityErrors = remainingErrors;
      } else {
        this.state.deviceEntityErrors = { ...this.state.deviceEntityErrors, [domain]: message(result.reason) };
      }
    });
    this.changed();
  }

  private async routeSnapshot(): Promise<void> {
    const state = this.state.snapshot?.state ?? "idle";
    if (isActive(state)) {
      this.state.view = "running";
      this.connectEvents();
      return;
    }
    this.state.view = "sessions";
  }

  private connectEvents(): void {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    this.eventConnection?.close();
    this.eventConnection = this.createEventConnection(sessionId, {
      onEvent: (event) => this.consumeEvent(event),
      onConnection: (connected) => {
        this.state.connectedToEvents = connected;
        this.changed();
      },
      onReconnect: () => { void this.refreshSnapshot(); },
    });
    this.eventConnection.connect();
  }

  private consumeEvent(event: SessionEvent): void {
    if ((event.type === "log" || event.type === "warning" || event.type === "checkpoint") && event.data.message) {
      this.state.logs = [...this.state.logs.slice(-39), event.data.message];
    }
    if (event.type === "sample" && typeof event.data.power === "number") {
      this.state.samples = [...this.state.samples.slice(-179), event.data.power];
    }
    if (event.snapshot) this.state.snapshot = event.snapshot;
    this.changed();
    if (this.state.snapshot && isTerminal(this.state.snapshot.state)) void this.enterResult();
  }

  private async refreshSnapshot(): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    try {
      this.state.snapshot = await this.api().getSession(sessionId);
      if (isTerminal(this.state.snapshot.state)) await this.enterResult();
    } catch {
      this.state.connectedToEvents = false;
    }
    this.changed();
  }

  private async enterResult(): Promise<void> {
    this.eventConnection?.close();
    this.state.connectedToEvents = false;
    if (this.state.view === "settings") this.settingsReturnView = "result";
    else this.state.view = "result";
    await this.loadResultArtifacts();
    await this.refreshSessions();
    this.changed();
  }

  private async refreshSessions(): Promise<void> {
    try {
      this.state.sessions = await this.api().getSessions();
    } catch (error) {
      this.state.errorMessage ||= `Could not refresh measurement sessions: ${message(error)}`;
    }
  }

  private resetDraft(request?: MeasurementRequest): void {
    this.eventConnection?.close();
    this.state.connectedToEvents = false;
    this.state.snapshot = { state: "idle" };
    this.state.request = request;
    this.state.selectedMeasureType = request?.measure_type;
    this.state.preflight = undefined;
    this.state.files = [];
    this.state.plotCollection = emptyPlots();
    this.state.logs = [];
    this.state.samples = [];
    this.state.contributionDraft = undefined;
    this.state.contributionFormValues = undefined;
    this.contributionTouchedFields.clear();
    this.state.contributionPreview = undefined;
    this.state.contributionResult = undefined;
    this.state.contributionError = "";
    this.state.contributionErrorField = undefined;
    this.clearError();
  }

  /**
   * Shared shape of every user-triggered command: mark the app busy, report a failure in the
   * error banner, and notify the view once before and once after the work.
   */
  private async run(work: () => Promise<void>): Promise<void> {
    this.state.busy = true;
    this.clearError();
    this.changed();
    try {
      await work();
    } catch (error) {
      this.setError(error);
    } finally {
      this.state.busy = false;
      this.changed();
    }
  }

  /** The same, for contribution work, which reports into its own busy flag and error banner. */
  private async runContribution(work: () => Promise<void>): Promise<void> {
    this.state.contributionBusy = true;
    this.state.contributionError = "";
    this.state.contributionErrorField = undefined;
    this.changed();
    try {
      await work();
    } catch (error) {
      this.state.contributionError = message(error);
      this.state.contributionErrorField = error instanceof ApiError ? error.field ?? undefined : undefined;
    } finally {
      this.state.contributionBusy = false;
      this.changed();
    }
  }

  /** Adopt the configuration a stored session was started with, so the draft and forms match it. */
  private async adoptRequest(request?: MeasurementRequest): Promise<void> {
    this.state.request = request;
    if (request) await this.loadTypeEntities(request.measure_type, request);
  }

  private async enterRunning(): Promise<void> {
    await this.refreshSessions();
    this.state.view = "running";
    this.connectEvents();
  }

  private async sessionCommand(label: string, command: () => Promise<SessionSnapshot>): Promise<void> {
    this.state.busy = true;
    this.changed();
    try {
      this.state.snapshot = await command();
    } catch (error) {
      this.state.logs = [...this.state.logs, `${label} failed: ${message(error)}`];
    } finally {
      this.state.busy = false;
      this.changed();
    }
  }

  private async loadResultArtifacts(): Promise<void> {
    const sessionId = this.state.snapshot?.session_id;
    if (!sessionId) return;
    this.state.contributionFormValues = undefined;
    this.contributionTouchedFields.clear();
    const [files, plots, calibration, auth, contribution, contributionStatus, manufacturers, deviceSpecifications, measureDevices] = await Promise.allSettled([
      this.api().getFiles(sessionId),
      this.api().getPlots(sessionId),
      this.api().getDummyLoadCalibration(),
      this.api().getContributionAuth(),
      this.api().getContributionDraft(sessionId),
      this.api().getContributionStatus(),
      this.api().getManufacturers(),
      this.api().getDeviceSpecifications(),
      this.api().getMeasureDevices(),
    ]);
    this.state.files = files.status === "fulfilled" ? files.value : [];
    this.state.plotCollection = plots.status === "fulfilled" ? plots.value : emptyPlots(["Plots could not be loaded."]);
    if (calibration.status === "fulfilled") this.state.dummyLoadCalibration = calibration.value;
    if (auth.status === "fulfilled") this.state.contributionAuth = auth.value;
    if (contribution.status === "fulfilled") {
      this.state.contributionDraft = contribution.value;
      this.state.contributionPreview = undefined;
      this.state.contributionError = "";
      this.state.contributionErrorField = undefined;
    } else {
      this.state.contributionDraft = undefined;
      this.state.contributionPreview = undefined;
    }
    if (contributionStatus.status === "fulfilled") this.restoreContributionStatus(contributionStatus.value);
    this.state.manufacturers = manufacturers.status === "fulfilled" ? manufacturers.value.manufacturers : [];
    this.state.deviceSpecificationFields = deviceSpecifications.status === "fulfilled"
      ? deviceSpecifications.value.device_types
      : {};
    this.state.measureDevices = measureDevices.status === "fulfilled" ? measureDevices.value.devices : [];
    this.state.measureDevicesError = measureDevices.status === "rejected" ? message(measureDevices.reason) : "";
  }

  /** Recover persisted contribution progress (e.g. after a reload or dropped connection mid-submit). */
  private restoreContributionStatus(status: ContributionStatus): void {
    if (!status.session_id || status.session_id !== this.state.snapshot?.session_id) return;
    if (status.state === "preview_ready" && status.preview) {
      this.state.contributionPreview = status.preview;
      return;
    }
    if (status.state === "submitted" && status.submission_url && !this.state.contributionResult) {
      if (status.preview) this.state.contributionPreview = status.preview;
      this.state.contributionResult = {
        status: "success",
        pull_request_url: status.submission_url,
        message: status.message ?? "Contribution submitted",
      };
      return;
    }
    if (status.state === "failed" && status.error && !this.state.contributionResult) {
      if (status.preview) this.state.contributionPreview = status.preview;
      this.state.contributionError = status.error;
      this.state.contributionErrorField = undefined;
    }
  }
}

const ACTIVE_STATES: ReadonlySet<SessionState> = new Set(["running", "awaiting_confirmation", "cancelling", "validating", "ready"]);
const TERMINAL_STATES: ReadonlySet<SessionState> = new Set(["completed", "failed", "cancelled", "resumable"]);

function isActive(state: SessionState): boolean {
  return ACTIVE_STATES.has(state);
}

function isTerminal(state: SessionState): boolean {
  return TERMINAL_STATES.has(state);
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}

function validRetryAfter(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
