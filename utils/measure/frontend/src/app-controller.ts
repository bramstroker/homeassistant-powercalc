import { ApiError } from "./api-client";
import { entityDomains } from "./measurement-kinds";
import type {
  AppSettings,
  Capabilities,
  ContributionAuthDeviceStatus,
  ContributionAuthState,
  ContributionDeviceFlow,
  ContributionPreview,
  ContributionPreviewRequest,
  ContributionResult,
  ContributionStatus,
  ContributionSubmitRequest,
  DeviceClass,
  DummyLoadCalibration,
  EntityCatalog,
  EntityDescriptor,
  MeasureDefinition,
  MeasureType,
  MeasurementRequest,
  PlotCollection,
  PowerMeterDiagnostic,
  PreflightResponse,
  SessionEvent,
  SessionFile,
  SessionSnapshot,
  SettingsSection,
  ShellyDiscoveryDevice,
  ShellyDiscoveryResponse,
} from "./types";

export type AppView = "loading" | "setup" | "review" | "running" | "result" | "settings";

export interface MeasureAppState {
  view: AppView;
  settingsSection?: SettingsSection;
  errorMessage: string;
  busy: boolean;
  connectedToEvents: boolean;
  snapshot?: SessionSnapshot;
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
  contributionAuth?: ContributionAuthState;
  contributionDeviceFlow?: ContributionDeviceFlow;
  contributionDeviceStatus?: ContributionAuthDeviceStatus;
  contributionDraft?: ContributionPreview;
  contributionPreview?: ContributionPreview;
  contributionResult?: ContributionResult;
  contributionBusy: boolean;
  contributionAuthBusy: boolean;
  contributionError: string;
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

export interface MeasureAppApi {
  getCapabilities(): Promise<Capabilities>;
  getMeasureDefinitions(): Promise<MeasureDefinition[]>;
  getSettings(): Promise<AppSettings>;
  getContributionAuth(): Promise<ContributionAuthState>;
  getContributionStatus(): Promise<ContributionStatus>;
  startContributionDeviceAuth(): Promise<ContributionDeviceFlow>;
  getContributionDeviceAuth(flowId: string): Promise<ContributionAuthDeviceStatus>;
  saveContributionToken(token: string): Promise<ContributionAuthState>;
  disconnectContributionAuth(): Promise<ContributionAuthState>;
  saveSettings(settings: AppSettings): Promise<AppSettings>;
  testPowerMeter(settings: AppSettings): Promise<PowerMeterDiagnostic>;
  getShellyDevices(): Promise<ShellyDiscoveryResponse>;
  getEntityCatalog(): Promise<EntityCatalog>;
  getEntitiesByDomain(domain: string): Promise<EntityDescriptor[]>;
  getEntitiesByDeviceClass(deviceClass: DeviceClass): Promise<EntityDescriptor[]>;
  getDummyLoadCalibration(): Promise<DummyLoadCalibration | null>;
  preflight(request: MeasurementRequest): Promise<PreflightResponse>;
  start(request: MeasurementRequest): Promise<SessionSnapshot>;
  getCurrent(): Promise<SessionSnapshot>;
  cancel(): Promise<SessionSnapshot>;
  confirm(): Promise<SessionSnapshot>;
  resume(): Promise<SessionSnapshot>;
  getFiles(): Promise<SessionFile[]>;
  getPlots(): Promise<PlotCollection>;
  getContributionDraft(): Promise<ContributionPreview>;
  previewContribution(request: ContributionPreviewRequest): Promise<ContributionPreview>;
  submitContribution(request: ContributionSubmitRequest): Promise<ContributionResult>;
}

export interface EventConnection {
  connect(): void;
  close(): void;
}

interface EventCallbacks {
  onEvent: (event: SessionEvent) => void;
  onConnection: (connected: boolean) => void;
  onReconnect: () => void;
}

type EventConnectionFactory = (callbacks: EventCallbacks) => EventConnection;

/** Framework-neutral application controller. Lit only observes the state mutations. */
export class MeasureAppController {
  private eventConnection?: EventConnection;
  private settingsReturnView: AppView = "setup";
  private powerMeterTestVersion = 0;
  private shellyDiscoveryVersion = 0;

  constructor(
    private readonly state: MeasureAppState,
    private readonly api: () => MeasureAppApi,
    private readonly createEventConnection: EventConnectionFactory,
    private readonly changed: () => void,
  ) {}

  dispose(): void {
    this.shellyDiscoveryVersion += 1;
    this.eventConnection?.close();
  }

  async boot(): Promise<void> {
    this.state.view = "loading";
    this.state.errorMessage = "";
    this.changed();
    try {
      const api = this.api();
      const currentPromise = api.getCurrent().catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return { state: "idle" } satisfies SessionSnapshot;
        throw error;
      });
      const calibrationPromise = this.refreshDummyLoadCalibration();
      const [capabilities, entities, settings, auth, snapshot, definitions] = await Promise.all([
        api.getCapabilities(),
        api.getEntityCatalog(),
        api.getSettings(),
        api.getContributionAuth().catch(() => ({ connected: false }) satisfies ContributionAuthState),
        currentPromise,
        api.getMeasureDefinitions(),
      ]);
      this.state.capabilities = capabilities;
      this.state.lights = entities.lights;
      this.state.powers = entities.powers;
      this.state.voltages = entities.voltages;
      this.state.settings = settings;
      this.state.contributionAuth = auth;
      this.state.snapshot = snapshot;
      this.state.definitions = definitions;
      await calibrationPromise;
      this.state.request = this.state.snapshot.request;
      if (this.state.request) await this.loadTypeEntities(this.state.request.measure_type);
      await this.routeSnapshot();
    } catch (error) {
      this.state.errorMessage = message(error);
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
    this.state.busy = true;
    this.state.errorMessage = "";
    this.state.request = request;
    this.changed();
    try {
      this.state.preflight = await this.api().preflight(request);
      this.state.view = "review";
    } catch (error) {
      this.state.errorMessage = message(error);
    } finally {
      this.state.busy = false;
      this.changed();
    }
  }

  backToSetup(): void {
    this.state.errorMessage = "";
    this.state.view = "setup";
    this.changed();
  }

  async start(): Promise<void> {
    if (!this.state.request) return;
    this.state.busy = true;
    this.state.errorMessage = "";
    this.state.samples = [];
    this.state.plotCollection = { partial: false, plots: [], warnings: [] };
    this.changed();
    try {
      this.state.snapshot = await this.api().start(this.state.request);
      this.state.view = "running";
      this.connectEvents();
    } catch (error) {
      this.state.errorMessage = message(error);
    } finally {
      this.state.busy = false;
      this.changed();
    }
  }

  async confirm(): Promise<void> {
    await this.sessionCommand("Confirmation", () => this.api().confirm());
  }

  async cancel(): Promise<void> {
    await this.sessionCommand("Cancellation", () => this.api().cancel());
  }

  async resume(): Promise<void> {
    this.state.busy = true;
    this.state.errorMessage = "";
    this.state.plotCollection = { partial: false, plots: [], warnings: [] };
    this.changed();
    try {
      this.state.snapshot = await this.api().resume();
      this.state.view = "running";
      this.connectEvents();
    } catch (error) {
      this.state.errorMessage = message(error);
    } finally {
      this.state.busy = false;
      this.changed();
    }
  }

  newMeasurement(): void {
    this.eventConnection?.close();
    this.state.snapshot = { state: "idle" };
    this.state.request = undefined;
    this.state.selectedMeasureType = undefined;
    this.state.preflight = undefined;
    this.state.files = [];
    this.state.plotCollection = { partial: false, plots: [], warnings: [] };
    this.state.logs = [];
    this.state.samples = [];
    this.state.contributionDraft = undefined;
    this.state.contributionPreview = undefined;
    this.state.contributionResult = undefined;
    this.state.contributionError = "";
    this.state.errorMessage = "";
    this.state.view = "setup";
    this.changed();
  }

  openSettings(section?: SettingsSection): void {
    if (this.state.view === "loading" || this.state.view === "settings") return;
    this.settingsReturnView = this.state.view;
    this.state.settingsSection = section;
    this.state.errorMessage = "";
    this.powerMeterTestVersion += 1;
    this.state.powerMeterTestResult = undefined;
    this.state.testingPowerMeter = false;
    this.state.view = "settings";
    this.changed();
    if (this.state.settings?.power_meter === "shelly") void this.discoverShellys();
  }

  closeSettings(): void {
    this.state.errorMessage = "";
    this.state.view = this.settingsReturnView;
    this.changed();
  }

  async testPowerMeter(settings: AppSettings): Promise<void> {
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

  async saveSettings(settings: AppSettings): Promise<void> {
    this.state.busy = true;
    this.state.errorMessage = "";
    this.changed();
    try {
      this.state.settings = await this.api().saveSettings(settings);
      [this.state.capabilities] = await Promise.all([
        this.api().getCapabilities(),
        this.refreshDummyLoadCalibration(),
      ]);
      this.state.view = this.settingsReturnView;
    } catch (error) {
      this.state.errorMessage = message(error);
    } finally {
      this.state.busy = false;
      this.changed();
    }
  }

  async startContributionDeviceAuth(): Promise<void> {
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.state.contributionDeviceStatus = undefined;
    this.changed();
    try {
      this.state.contributionDeviceFlow = await this.api().startContributionDeviceAuth();
    } catch (error) {
      this.state.contributionAuthError = message(error);
    } finally {
      this.state.contributionAuthBusy = false;
      this.changed();
    }
  }

  async checkContributionDeviceAuth(): Promise<void> {
    const flowId = this.state.contributionDeviceFlow?.flow_id;
    if (!flowId) return;
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.changed();
    try {
      const status = await this.api().getContributionDeviceAuth(flowId);
      this.state.contributionDeviceStatus = status;
      if (status.auth) this.state.contributionAuth = status.auth;
      if (status.status === "authorized") this.state.contributionDeviceFlow = undefined;
    } catch (error) {
      this.state.contributionAuthError = message(error);
    } finally {
      this.state.contributionAuthBusy = false;
      this.changed();
    }
  }

  async saveContributionToken(token: string): Promise<void> {
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.changed();
    try {
      this.state.contributionAuth = await this.api().saveContributionToken(token);
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
    this.state.contributionBusy = true;
    this.state.contributionError = "";
    this.changed();
    try {
      this.state.contributionPreview = await this.api().previewContribution(request);
      this.state.contributionResult = undefined;
    } catch (error) {
      this.state.contributionError = message(error);
    } finally {
      this.state.contributionBusy = false;
      this.changed();
    }
  }

  async submitContribution(request: ContributionSubmitRequest): Promise<void> {
    this.state.contributionBusy = true;
    this.state.contributionError = "";
    this.changed();
    try {
      this.state.contributionResult = await this.api().submitContribution(request);
    } catch (error) {
      this.state.contributionError = message(error);
    } finally {
      this.state.contributionBusy = false;
      this.changed();
    }
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

  private async loadTypeEntities(type: MeasureType): Promise<void> {
    const definition = this.state.definitions.find((candidate) => candidate.measure_type === type);
    if (definition) await this.ensureEntityDomains(entityDomains(definition));
  }

  private async ensureEntityDomains(domains: string[]): Promise<void> {
    const pending = [...new Set(domains)].filter((domain) => !(domain in this.state.deviceEntities));
    if (!pending.length) return;
    const results = await Promise.allSettled(pending.map((domain) => this.api().getEntitiesByDomain(domain)));
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
    if (isTerminal(state)) {
      this.state.view = "result";
      await this.loadResultArtifacts();
      return;
    }
    this.state.view = "setup";
  }

  private connectEvents(): void {
    this.eventConnection?.close();
    this.eventConnection = this.createEventConnection({
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
    if ((event.type === "log" || event.type === "checkpoint") && event.data.message) {
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
    try {
      this.state.snapshot = await this.api().getCurrent();
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
    this.changed();
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
    const [files, plots, calibration, auth, contribution, contributionStatus] = await Promise.allSettled([
      this.api().getFiles(),
      this.api().getPlots(),
      this.api().getDummyLoadCalibration(),
      this.api().getContributionAuth(),
      this.api().getContributionDraft(),
      this.api().getContributionStatus(),
    ]);
    this.state.files = files.status === "fulfilled" ? files.value : [];
    this.state.plotCollection = plots.status === "fulfilled"
      ? plots.value
      : { partial: false, plots: [], warnings: ["Plots could not be loaded."] };
    if (calibration.status === "fulfilled") this.state.dummyLoadCalibration = calibration.value;
    if (auth.status === "fulfilled") this.state.contributionAuth = auth.value;
    if (contribution.status === "fulfilled") {
      this.state.contributionDraft = contribution.value;
      this.state.contributionPreview = undefined;
      this.state.contributionError = "";
    } else {
      this.state.contributionDraft = undefined;
      this.state.contributionPreview = undefined;
    }
    if (contributionStatus.status === "fulfilled") this.restoreContributionStatus(contributionStatus.value);
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
    }
  }
}

function isActive(state: SessionSnapshot["state"]): boolean {
  return ["running", "awaiting_confirmation", "cancelling", "validating", "ready"].includes(state);
}

function isTerminal(state: SessionSnapshot["state"]): boolean {
  return ["completed", "failed", "cancelled", "resumable"].includes(state);
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}
