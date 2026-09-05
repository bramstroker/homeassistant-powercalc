import type { SessionSummary } from "../../types";
import "./view";

describe("sessions view", () => {
  it("offers retained-session actions and confirms deletion inline", async () => {
    const element = document.createElement("measure-sessions-view") as HTMLElement & {
      sessions: SessionSummary[];
      diagnosticsUrl: (sessionId: string) => string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.sessions = [{
      session_id: "session-1",
      state: "cancelled",
      created_at: "2026-08-13T10:00:00Z",
      updated_at: "2026-08-13T10:05:00Z",
      measure_type: "light",
      model_id: "LCT010",
      product_name: "Hue lamp",
      measure_device: "Desk meter",
      completed: 2,
      total: 4,
      percent: 50,
      can_resume: true,
      file_count: 2,
      size: 2048,
      active: false,
    }];
    element.diagnosticsUrl = (sessionId) => `http://ha.local/api/sessions/${sessionId}/diagnostics`;
    document.body.append(element);
    await element.updateComplete;

    const labels = [...element.shadowRoot.querySelectorAll("button")].map((button) => button.textContent?.trim());
    expect(labels).toEqual(expect.arrayContaining(["New measurement", "Open", "Resume", "Measure again", "Delete"]));
    const measureAgain = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Measure again");
    const tooltip = element.shadowRoot.querySelector<HTMLElement>('[role="tooltip"]');
    expect(tooltip?.textContent).toBe("Start a new measurement using these settings");
    expect(measureAgain?.getAttribute("aria-describedby")).toBe(tooltip?.id);
    const diagnostics = element.shadowRoot.querySelector<HTMLAnchorElement>('a[download]');
    expect(diagnostics?.href).toContain("/api/sessions/session-1/diagnostics");
    expect(diagnostics?.classList.contains("action-button")).toBe(true);
    expect(element.shadowRoot.querySelectorAll("button .icon, .action-button .icon")).toHaveLength(6);

    const deleted = new Promise<string>((resolve) => element.addEventListener("delete", (event) => resolve((event as CustomEvent<string>).detail)));
    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Delete")?.click();
    await element.updateComplete;
    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Confirm delete")?.click();

    await expect(deleted).resolves.toBe("session-1");
  });
});
