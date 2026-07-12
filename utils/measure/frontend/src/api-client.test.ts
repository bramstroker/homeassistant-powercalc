import { MeasureApiClient, SessionEventStream, apiUrl } from "./api-client";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("MeasureApiClient", () => {
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

  it("normalizes entity response envelopes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response({ entities: [{ entity_id: "light.desk", name: "Desk" }] }));
    const entities = await new MeasureApiClient(fetcher, "http://ha.local/prefix/").getEntities("light");
    expect(entities).toEqual([{ entity_id: "light.desk", name: "Desk" }]);
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
    listeners.get("progress")?.(new MessageEvent("progress", { data: JSON.stringify({ type: "progress", progress: { completed: 2, total: 4 } }) }));

    expect(onConnection).toHaveBeenCalledWith(true);
    expect(onReconnect).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "progress" }));
    stream.close();
    expect(fake.close).toHaveBeenCalledOnce();
  });
});
