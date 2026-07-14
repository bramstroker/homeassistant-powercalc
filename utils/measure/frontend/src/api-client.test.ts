import { MeasureApiClient, SessionEventStream, apiUrl } from "./api-client";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("MeasureApiClient", () => {
  it("binds the browser fetch implementation to its global receiver", async () => {
    const browserFetch = vi.fn<typeof fetch>().mockResolvedValue(response({ modes: [], defaults: {} }));
    vi.stubGlobal("fetch", browserFetch);

    await new MeasureApiClient(undefined, "http://ha.local/prefix/").getCapabilities();

    expect(browserFetch).toHaveBeenCalledWith(
      new URL("http://ha.local/prefix/api/capabilities"),
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("keeps requests and downloads below the ingress prefix", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ modes: [], defaults: {} }));
    const client = new MeasureApiClient(fetcher, "http://ha.local/api/hassio_ingress/token/");

    await client.getCapabilities();

    expect(fetcher).toHaveBeenCalledWith(
      new URL("http://ha.local/api/hassio_ingress/token/api/capabilities"),
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    expect(client.fileUrl("model data.json")).toBe("http://ha.local/api/hassio_ingress/token/api/session/current/files/model%20data.json");
    expect(apiUrl("api/entities", "http://ha.local/prefix/").pathname).toBe("/prefix/api/entities");
  });

  it("loads entities by Home Assistant domain or device class", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => response([{ entity_id: "light.desk", name: "Desk" }]));
    const client = new MeasureApiClient(fetcher, "http://ha.local/prefix/");

    const lights = await client.getEntitiesByDomain("light");
    const powers = await client.getEntitiesByDeviceClass("power");

    expect(fetcher).toHaveBeenNthCalledWith(1, new URL("http://ha.local/prefix/api/entities?domain=light"), expect.anything());
    expect(fetcher).toHaveBeenNthCalledWith(2, new URL("http://ha.local/prefix/api/entities?device_class=power"), expect.anything());
    expect(lights).toEqual([{ entity_id: "light.desk", name: "Desk" }]);
    expect(powers).toEqual([{ entity_id: "light.desk", name: "Desk" }]);
  });

  it("surfaces stable API errors", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ code: "active_session", message: "Already measuring", field: null }, 409));
    await expect(new MeasureApiClient(fetcher, "http://ha.local/prefix/").cancel()).rejects.toEqual(
      expect.objectContaining({ status: 409, code: "active_session", message: "Already measuring" }),
    );
  });
});

describe("SessionEventStream", () => {
  it("uses EventSource reconnect and refreshes the authoritative snapshot on open", () => {
    const listeners = new Map<string, EventListener>();
    const fake = {
      close: vi.fn(),
      onopen: null as (() => void) | null,
      onerror: null as (() => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      addEventListener: vi.fn((type: string, listener: EventListener) => listeners.set(type, listener)),
    };
    const onEvent = vi.fn();
    const onConnection = vi.fn();
    const onReconnect = vi.fn();
    const stream = new SessionEventStream("events", onEvent, onConnection, onReconnect, () => fake as unknown as EventSource);

    stream.connect();
    fake.onopen?.();
    listeners.get("progress")?.(new MessageEvent("progress", {
      data: JSON.stringify({ sequence: 2, type: "progress", data: { completed: 2, total: 4 } }),
    }));

    expect(onConnection).toHaveBeenCalledWith(true);
    expect(onReconnect).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "progress" }));
    stream.close();
    expect(fake.close).toHaveBeenCalledOnce();
  });

  it("consumes named heartbeat events to refresh the snapshot", () => {
    const listeners = new Map<string, EventListener>();
    const fake = {
      close: vi.fn(),
      onopen: null as (() => void) | null,
      onerror: null as (() => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      addEventListener: vi.fn((type: string, listener: EventListener) => listeners.set(type, listener)),
    };
    const onEvent = vi.fn();
    const stream = new SessionEventStream("events", onEvent, vi.fn(), vi.fn(), () => fake as unknown as EventSource);

    stream.connect();
    listeners.get("heartbeat")?.(new MessageEvent("heartbeat", {
      data: JSON.stringify({ sequence: 1, type: "heartbeat", data: {}, snapshot: { state: "running" } }),
    }));

    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "heartbeat", snapshot: { state: "running" } }));
  });
});
