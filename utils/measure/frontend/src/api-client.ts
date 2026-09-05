import { SESSION_EVENT_TYPES } from "./types";
import type {
  ApiErrorBody,
  AppSettings,
  AppSettingsUpdate,
  Capabilities,
  ContributionAuthDeviceStatus,
  ContributionAuthState,
  ContributionDeviceFlow,
  ContributionPreview,
  ContributionPreviewRequest,
  ContributionResult,
  ContributionStatus,
  ContributionSubmitRequest,
  ContributionTokenRequest,
  DeviceClass,
  DummyLoadCalibration,
  DeviceSpecificationCatalog,
  EntityCatalog,
  EntityDescriptor,
  ErrorHelp,
  MeasurementRequest,
  MeasureDefinition,
  MeasureDeviceCatalog,
  ManufacturerCatalog,
  PlotCollection,
  PowerMeterDiagnostic,
  PreflightResponse,
  SessionEvent,
  SessionFile,
  SessionSnapshot,
  SessionSummary,
  ShellyDiscoveryResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "request_failed",
    readonly field: string | null = null,
    readonly help?: ErrorHelp,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type Fetcher = typeof fetch;

/** Resolve against the document base so every request retains the HA ingress prefix. */
export function apiUrl(path: string, base = document.baseURI): URL {
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  return new URL(path.replace(/^\//, ""), normalizedBase);
}

export class MeasureApiClient {
  constructor(
    private readonly fetcher: Fetcher = globalThis.fetch.bind(globalThis),
    private readonly base = document.baseURI,
  ) {}

  getCapabilities(): Promise<Capabilities> {
    return this.request("api/capabilities");
  }

  getMeasureDefinitions(): Promise<MeasureDefinition[]> {
    return this.request("api/measure-definitions");
  }

  getMeasureDevices(): Promise<MeasureDeviceCatalog> {
    return this.request("api/library/measure-devices");
  }

  getManufacturers(): Promise<ManufacturerCatalog> {
    return this.request("api/library/manufacturers");
  }

  getDeviceSpecifications(): Promise<DeviceSpecificationCatalog> {
    return this.request("api/library/device-specifications");
  }

  getSettings(): Promise<AppSettings> {
    return this.request("api/settings");
  }

  getContributionAuth(): Promise<ContributionAuthState> {
    return this.request("api/contribution/auth");
  }

  startContributionDeviceAuth(): Promise<ContributionDeviceFlow> {
    return this.request("api/contribution/auth/device", { method: "POST" });
  }

  getContributionDeviceAuth(flowId: string): Promise<ContributionAuthDeviceStatus> {
    return this.request(`api/contribution/auth/device/${encodeURIComponent(flowId)}`, { method: "POST" });
  }

  getContributionStatus(): Promise<ContributionStatus> {
    return this.request("api/contribution/status");
  }

  preparedProfileUrl(sessionId: string, jobId: string): string {
    return apiUrl(
      `api/sessions/${encodeURIComponent(sessionId)}/contribution/${encodeURIComponent(jobId)}/profile.zip`,
      this.base,
    ).toString();
  }

  saveContributionToken(token: string): Promise<ContributionAuthState> {
    const body: ContributionTokenRequest = { token };
    return this.request("api/contribution/auth", { method: "PUT", body: JSON.stringify(body) });
  }

  disconnectContributionAuth(): Promise<ContributionAuthState> {
    return this.request("api/contribution/auth", { method: "DELETE" });
  }

  saveSettings(settings: AppSettingsUpdate): Promise<AppSettings> {
    return this.request("api/settings", { method: "PUT", body: JSON.stringify(settings) });
  }

  testPowerMeter(settings: AppSettingsUpdate): Promise<PowerMeterDiagnostic> {
    return this.request("api/settings/test-power-meter", { method: "POST", body: JSON.stringify(settings) });
  }

  getShellyDevices(): Promise<ShellyDiscoveryResponse> {
    return this.request("api/power-meters/shelly");
  }

  getEntityCatalog(): Promise<EntityCatalog> {
    return this.request<EntityCatalog>("api/entity-catalog");
  }

  getEntitiesByDomain(domain: string): Promise<EntityDescriptor[]> {
    return this.request<EntityDescriptor[]>(`api/entities?domain=${encodeURIComponent(domain)}`);
  }

  getAllEntities(): Promise<EntityDescriptor[]> {
    return this.request<EntityDescriptor[]>("api/entities?all=true");
  }

  getEntitiesByDeviceClass(deviceClass: DeviceClass): Promise<EntityDescriptor[]> {
    return this.request<EntityDescriptor[]>(`api/entities?device_class=${encodeURIComponent(deviceClass)}`);
  }

  getDummyLoadCalibration(): Promise<DummyLoadCalibration | null> {
    return this.request<DummyLoadCalibration | null>("api/dummy-load/calibration");
  }

  preflight(request: MeasurementRequest): Promise<PreflightResponse> {
    return this.request("api/preflight", { method: "POST", body: JSON.stringify(request) });
  }

  start(request: MeasurementRequest): Promise<SessionSnapshot> {
    return this.request("api/sessions", { method: "POST", body: JSON.stringify(request) });
  }

  getSessions(): Promise<SessionSummary[]> {
    return this.request("api/sessions");
  }

  getSession(sessionId: string): Promise<SessionSnapshot> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}`);
  }

  deleteSession(sessionId: string): Promise<void> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }, "none");
  }

  cancel(sessionId: string): Promise<SessionSnapshot> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}/cancel`, { method: "POST" });
  }

  confirm(sessionId: string): Promise<SessionSnapshot> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}/confirm`, { method: "POST" });
  }

  resume(sessionId: string): Promise<SessionSnapshot> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}/resume`, { method: "POST" });
  }

  getFiles(sessionId: string): Promise<SessionFile[]> {
    return this.request<SessionFile[]>(`api/sessions/${encodeURIComponent(sessionId)}/files`);
  }

  getPlots(sessionId: string): Promise<PlotCollection> {
    return this.request<PlotCollection>(`api/sessions/${encodeURIComponent(sessionId)}/plots`);
  }

  getContributionDraft(sessionId: string): Promise<ContributionPreview> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}/contribution`);
  }

  previewContribution(sessionId: string, request: ContributionPreviewRequest): Promise<ContributionPreview> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}/contribution/preview`, { method: "POST", body: JSON.stringify(request) });
  }

  submitContribution(sessionId: string, request: ContributionSubmitRequest): Promise<ContributionResult> {
    return this.request(`api/sessions/${encodeURIComponent(sessionId)}/contribution`, { method: "POST", body: JSON.stringify(request) });
  }

  fileUrl(sessionId: string, name: string): string {
    return apiUrl(`api/sessions/${encodeURIComponent(sessionId)}/files/${encodeURIComponent(name)}`, this.base).toString();
  }

  diagnosticsUrl(sessionId: string): string {
    return apiUrl(`api/sessions/${encodeURIComponent(sessionId)}/diagnostics`, this.base).toString();
  }

  eventsUrl(sessionId: string): string {
    return apiUrl(`api/sessions/${encodeURIComponent(sessionId)}/events`, this.base).toString();
  }

  private async request<T>(path: string, init: RequestInit = {}, body: "json" | "none" = "json"): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    headers.set("Accept", "application/json");
    const response = await this.fetcher(apiUrl(path, this.base), { ...init, headers });
    if (!response.ok) throw await this.error(response);
    return body === "none" ? (undefined as T) : ((await response.json()) as T);
  }

  private async error(response: Response): Promise<ApiError> {
    let body: Partial<ApiErrorBody> & { detail?: unknown } = {};
    try {
      body = (await response.json()) as Partial<ApiErrorBody>;
    } catch {
      // Keep the stable fallback for non-JSON proxy and server errors.
    }
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    const help = body.help_url && body.help_label ? { url: body.help_url, label: body.help_label } : undefined;
    return new ApiError(body.message ?? detail ?? `Request failed (${response.status})`, response.status, body.code, body.field, help);
  }
}

type EventSourceFactory = (url: string) => EventSource;

export class SessionEventStream {
  private source?: EventSource;

  constructor(
    private readonly url: string,
    private readonly onEvent: (event: SessionEvent) => void,
    private readonly onConnection: (connected: boolean) => void,
    private readonly onReconnect: () => void,
    private readonly createSource: EventSourceFactory = (eventUrl) => new EventSource(eventUrl),
  ) {}

  connect(): void {
    this.close();
    const source = this.createSource(this.url);
    this.source = source;
    source.onopen = () => {
      this.onConnection(true);
      this.onReconnect();
    };
    source.onerror = () => this.onConnection(false);
    source.onmessage = (event) => this.consume(event.data);
    for (const type of SESSION_EVENT_TYPES) {
      source.addEventListener(type, (event) => this.consume((event as MessageEvent<string>).data));
    }
  }

  close(): void {
    this.source?.close();
    this.source = undefined;
  }

  private consume(data: string): void {
    try {
      const event = JSON.parse(data) as Partial<SessionEvent>;
      if (typeof event.sequence !== "number" || typeof event.type !== "string" || typeof event.data !== "object" || event.data === null) {
        throw new Error("Invalid event envelope");
      }
      this.onEvent(event as SessionEvent);
    } catch {
      this.onConnection(false);
      this.onEvent({ sequence: 0, type: "log", data: { message: "Received an invalid event from the measure app." } });
    }
  }
}
