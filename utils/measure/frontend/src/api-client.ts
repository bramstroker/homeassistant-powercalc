import { SESSION_EVENT_TYPES } from "./types";
import {
  decodeApiError,
  decodeCapabilities,
  decodeContributionAuth,
  decodeContributionAuthDeviceStatus,
  decodeContributionDeviceFlow,
  decodeContributionPreview,
  decodeContributionResult,
  decodeContributionStatus,
  decodeDeviceSpecifications,
  decodeDummyLoadCalibration,
  decodeEntities,
  decodeEntityCatalog,
  decodeManufacturers,
  decodeMeasureDefinitions,
  decodeMeasureDevices,
  decodePlots,
  decodePowerMeterDiagnostic,
  decodePreflight,
  decodeSessionEnvelope,
  decodeSessionFiles,
  decodeSessionSnapshot,
  decodeSessionSummaries,
  decodeSettings,
  decodeShellyDiscovery,
} from "./api-decoders";
import type { Decoder } from "./api-decoders";
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
    return this.requestJson("api/capabilities", decodeCapabilities);
  }

  getMeasureDefinitions(): Promise<MeasureDefinition[]> {
    return this.requestJson("api/measure-definitions", decodeMeasureDefinitions);
  }

  getMeasureDevices(): Promise<MeasureDeviceCatalog> {
    return this.requestJson("api/library/measure-devices", decodeMeasureDevices);
  }

  getManufacturers(): Promise<ManufacturerCatalog> {
    return this.requestJson("api/library/manufacturers", decodeManufacturers);
  }

  getDeviceSpecifications(): Promise<DeviceSpecificationCatalog> {
    return this.requestJson("api/library/device-specifications", decodeDeviceSpecifications);
  }

  getSettings(): Promise<AppSettings> {
    return this.requestJson("api/settings", decodeSettings);
  }

  getContributionAuth(): Promise<ContributionAuthState> {
    return this.requestJson("api/contribution/auth", decodeContributionAuth);
  }

  startContributionDeviceAuth(): Promise<ContributionDeviceFlow> {
    return this.requestJson("api/contribution/auth/device", decodeContributionDeviceFlow, { method: "POST" });
  }

  getContributionDeviceAuth(flowId: string): Promise<ContributionAuthDeviceStatus> {
    return this.requestJson(`api/contribution/auth/device/${encodeURIComponent(flowId)}`, decodeContributionAuthDeviceStatus, { method: "POST" });
  }

  getContributionStatus(): Promise<ContributionStatus> {
    return this.requestJson("api/contribution/status", decodeContributionStatus);
  }

  preparedProfileUrl(sessionId: string, jobId: string): string {
    return apiUrl(
      `api/sessions/${encodeURIComponent(sessionId)}/contribution/${encodeURIComponent(jobId)}/profile.zip`,
      this.base,
    ).toString();
  }

  saveContributionToken(token: string): Promise<ContributionAuthState> {
    const body: ContributionTokenRequest = { token };
    return this.requestJson("api/contribution/auth", decodeContributionAuth, { method: "PUT", body: JSON.stringify(body) });
  }

  disconnectContributionAuth(): Promise<ContributionAuthState> {
    return this.requestJson("api/contribution/auth", decodeContributionAuth, { method: "DELETE" });
  }

  saveSettings(settings: AppSettingsUpdate): Promise<AppSettings> {
    return this.requestJson("api/settings", decodeSettings, { method: "PUT", body: JSON.stringify(settings) });
  }

  testPowerMeter(settings: AppSettingsUpdate): Promise<PowerMeterDiagnostic> {
    return this.requestJson("api/settings/test-power-meter", decodePowerMeterDiagnostic, { method: "POST", body: JSON.stringify(settings) });
  }

  getShellyDevices(): Promise<ShellyDiscoveryResponse> {
    return this.requestJson("api/power-meters/shelly", decodeShellyDiscovery);
  }

  getEntityCatalog(): Promise<EntityCatalog> {
    return this.requestJson("api/entity-catalog", decodeEntityCatalog);
  }

  getEntitiesByDomain(domain: string): Promise<EntityDescriptor[]> {
    return this.requestJson(`api/entities?domain=${encodeURIComponent(domain)}`, decodeEntities);
  }

  getAllEntities(): Promise<EntityDescriptor[]> {
    return this.requestJson("api/entities?all=true", decodeEntities);
  }

  getEntitiesByDeviceClass(deviceClass: DeviceClass): Promise<EntityDescriptor[]> {
    return this.requestJson(`api/entities?device_class=${encodeURIComponent(deviceClass)}`, decodeEntities);
  }

  getDummyLoadCalibration(): Promise<DummyLoadCalibration | null> {
    return this.requestJson("api/dummy-load/calibration", decodeDummyLoadCalibration);
  }

  preflight(request: MeasurementRequest): Promise<PreflightResponse> {
    return this.requestJson("api/preflight", decodePreflight, { method: "POST", body: JSON.stringify(request) });
  }

  start(request: MeasurementRequest): Promise<SessionSnapshot> {
    return this.requestJson("api/sessions", decodeSessionSnapshot, { method: "POST", body: JSON.stringify(request) });
  }

  getSessions(): Promise<SessionSummary[]> {
    return this.requestJson("api/sessions", decodeSessionSummaries);
  }

  getSession(sessionId: string): Promise<SessionSnapshot> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}`, decodeSessionSnapshot);
  }

  deleteSession(sessionId: string): Promise<void> {
    return this.requestEmpty(`api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  }

  cancel(sessionId: string): Promise<SessionSnapshot> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/cancel`, decodeSessionSnapshot, { method: "POST" });
  }

  confirm(sessionId: string): Promise<SessionSnapshot> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/confirm`, decodeSessionSnapshot, { method: "POST" });
  }

  resume(sessionId: string): Promise<SessionSnapshot> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/resume`, decodeSessionSnapshot, { method: "POST" });
  }

  analyse(sessionId: string): Promise<SessionSnapshot> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/analyse`, decodeSessionSnapshot, { method: "POST" });
  }

  getFiles(sessionId: string): Promise<SessionFile[]> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/files`, decodeSessionFiles);
  }

  getJsonFile(sessionId: string, name: string): Promise<unknown> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/files/${encodeURIComponent(name)}`, (value) => value);
  }

  getPlots(sessionId: string): Promise<PlotCollection> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/plots`, decodePlots);
  }

  getContributionDraft(sessionId: string): Promise<ContributionPreview> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/contribution`, decodeContributionPreview);
  }

  previewContribution(sessionId: string, request: ContributionPreviewRequest): Promise<ContributionPreview> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/contribution/preview`, decodeContributionPreview, { method: "POST", body: JSON.stringify(request) });
  }

  submitContribution(sessionId: string, request: ContributionSubmitRequest): Promise<ContributionResult> {
    return this.requestJson(`api/sessions/${encodeURIComponent(sessionId)}/contribution`, decodeContributionResult, { method: "POST", body: JSON.stringify(request) });
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

  private async fetch(path: string, init: RequestInit): Promise<Response> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    headers.set("Accept", "application/json");
    const response = await this.fetcher(apiUrl(path, this.base), { ...init, headers });
    if (!response.ok) throw await this.error(response);
    return response;
  }

  private async requestJson<T>(path: string, decode: Decoder<T>, init: RequestInit = {}): Promise<T> {
    const response = await this.fetch(path, init);
    return decode(await response.json());
  }

  private async requestEmpty(path: string, init: RequestInit = {}): Promise<void> {
    await this.fetch(path, init);
  }

  private async error(response: Response): Promise<ApiError> {
    let body: Partial<ApiErrorBody> & { detail?: unknown } = {};
    try {
      body = decodeApiError(await response.json());
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
      source.addEventListener(type, (event) => {
        if ("data" in event && typeof event.data === "string") this.consume(event.data);
      });
    }
  }

  close(): void {
    this.source?.close();
    this.source = undefined;
  }

  private consume(data: string): void {
    let decoded: ReturnType<typeof decodeSessionEnvelope>;
    try {
      decoded = decodeSessionEnvelope(JSON.parse(data));
    } catch {
      this.onConnection(false);
      this.onEvent({ sequence: 0, type: "log", data: { message: "Received an invalid event from the measure app." } });
      return;
    }
    if (decoded.event) this.onEvent(decoded.event);
    else if (decoded.snapshot) this.onEvent({ sequence: 0, type: "heartbeat", data: {}, snapshot: decoded.snapshot });
  }
}
