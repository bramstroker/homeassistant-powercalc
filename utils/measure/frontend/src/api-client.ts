import type {
  ApiErrorBody,
  AppSettings,
  Capabilities,
  DeviceClass,
  EntityDescriptor,
  MeasurementRequest,
  MeasureDefinition,
  PowerMeterDiagnostic,
  PreflightResponse,
  SessionEvent,
  SessionFile,
  SessionSnapshot,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "request_failed",
    readonly field: string | null = null,
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

  getSettings(): Promise<AppSettings> {
    return this.request("api/settings");
  }

  saveSettings(settings: AppSettings): Promise<AppSettings> {
    return this.request("api/settings", { method: "PUT", body: JSON.stringify(settings) });
  }

  testPowerMeter(settings: AppSettings): Promise<PowerMeterDiagnostic> {
    return this.request("api/settings/test-power-meter", { method: "POST", body: JSON.stringify(settings) });
  }

  getEntitiesByDomain(domain: string): Promise<EntityDescriptor[]> {
    return this.request<EntityDescriptor[]>(`api/entities?domain=${encodeURIComponent(domain)}`);
  }

  getEntitiesByDeviceClass(deviceClass: DeviceClass): Promise<EntityDescriptor[]> {
    return this.request<EntityDescriptor[]>(`api/entities?device_class=${encodeURIComponent(deviceClass)}`);
  }

  preflight(request: MeasurementRequest): Promise<PreflightResponse> {
    return this.request("api/preflight", { method: "POST", body: JSON.stringify(request) });
  }

  start(request: MeasurementRequest): Promise<SessionSnapshot> {
    return this.request("api/sessions", { method: "POST", body: JSON.stringify(request) });
  }


  getCurrent(): Promise<SessionSnapshot> {
    return this.request("api/session/current");
  }

  cancel(): Promise<SessionSnapshot> {
    return this.request("api/session/current", { method: "DELETE" });
  }

  confirm(): Promise<SessionSnapshot> {
    return this.request("api/session/current/confirm", { method: "POST" });
  }

  resume(): Promise<SessionSnapshot> {
    return this.request("api/session/current/resume", { method: "POST" });
  }

  getFiles(): Promise<SessionFile[]> {
    return this.request<SessionFile[]>("api/session/current/files");
  }

  fileUrl(name: string): string {
    return apiUrl(`api/session/current/files/${encodeURIComponent(name)}`, this.base).toString();
  }

  eventsUrl(): string {
    return apiUrl("api/session/current/events", this.base).toString();
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    headers.set("Accept", "application/json");
    const response = await this.fetcher(apiUrl(path, this.base), { ...init, headers });
    if (!response.ok) {
      let body: Partial<ApiErrorBody> & { detail?: unknown } = {};
      try {
        body = (await response.json()) as Partial<ApiErrorBody>;
      } catch {
        // Keep the stable fallback for non-JSON proxy and server errors.
      }
      const detail = typeof body.detail === "string" ? body.detail : undefined;
      throw new ApiError(body.message ?? detail ?? `Request failed (${response.status})`, response.status, body.code, body.field);
    }
    return (await response.json()) as T;
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
    for (const type of ["progress", "state", "warning", "log", "checkpoint", "heartbeat", "sample", "operating_point"] as const) {
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
