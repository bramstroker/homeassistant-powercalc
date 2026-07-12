import { LitElement, css, html, nothing } from "lit";
import { ApiError, MeasureApiClient, SessionEventStream } from "../api-client";
import type { AppSettings, Capabilities, EntityDescriptor, MeasurementRequest, PreflightResponse, SessionEvent, SessionFile, SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";
import "./preflight-view";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

type View = "loading" | "setup" | "review" | "running" | "result" | "settings";

export class AppShell extends LitElement {
  static readonly properties = {
    view: { state: true }, loadingMessage: { state: true }, errorMessage: { state: true }, busy: { state: true },
    connectedToEvents: { state: true }, snapshot: { state: true }, request: { state: true }, preflight: { state: true },
    files: { state: true }, logs: { state: true }, settings: { state: true },
  };

  view: View = "loading";
  loadingMessage = "Connecting to Home Assistant…";
  errorMessage = "";
  busy = false;
  connectedToEvents = false;
  snapshot?: SessionSnapshot;
  request?: MeasurementRequest;
  preflight?: PreflightResponse;
  files: SessionFile[] = [];
  logs: string[] = [];
  capabilities?: Capabilities;
  lights: EntityDescriptor[] = [];
  powers: EntityDescriptor[] = [];
  voltages: EntityDescriptor[] = [];
  settings?: AppSettings;

  private readonly api = new MeasureApiClient();
  private eventStream?: SessionEventStream;
  private settingsReturnView: View = "setup";

  static readonly styles = [sharedStyles, css`
    :host { display: block; min-height: 100vh; background: var(--canvas); }
    .shell { width: min(980px, calc(100% - 2rem)); margin: 0 auto; padding: clamp(1.2rem, 5vw, 3.5rem) 0 4rem; }
    header { display: grid; grid-template-columns: 1fr auto; gap: 2rem; align-items: end; margin-bottom: clamp(1.5rem, 5vw, 3rem); }
    .brand { display: flex; align-items: center; gap: 0.7rem; margin-bottom: 1.3rem; color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.16em; text-transform: uppercase; }
    .brand-mark { display: inline-grid; grid-template-columns: repeat(3, 4px); align-items: end; gap: 3px; height: 16px; }
    .brand-mark i { display: block; width: 4px; background: var(--signal); } .brand-mark i:nth-child(1) { height: 35%; } .brand-mark i:nth-child(2) { height: 100%; } .brand-mark i:nth-child(3) { height: 65%; }
    h1 { max-width: 650px; margin: 0; font-size: clamp(2.2rem, 7vw, 4.8rem); line-height: 0.92; letter-spacing: -0.045em; }
    .subtitle { max-width: 480px; margin: 1.2rem 0 0; color: var(--muted); font-size: 1rem; line-height: 1.6; }
    .header-aside { display: grid; gap: 1.1rem; justify-items: end; }
    .settings-toggle { min-height: 0; padding: 0.4rem 0.8rem; border-radius: 999px; font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 0.45rem; }
    .settings-toggle::before { content: "⚙"; font-size: 0.95rem; }
    .sequence { display: grid; gap: 0.5rem; justify-items: end; }
    .sequence > span { width: 68px; height: 3px; border-radius: 99px; background: var(--line); }
    .sequence > span.active, .sequence > span.done { background: var(--signal); }
    .loading { min-height: 260px; display: grid; place-items: center; text-align: center; }
    .pulse { width: 40px; height: 40px; margin: 0 auto 1rem; border: 2px solid var(--line); border-top-color: var(--signal); border-radius: 50%; animation: spin 850ms linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    footer { margin-top: 1rem; color: var(--muted); font-size: 0.72rem; text-align: right; }
    @media (max-width: 700px) { header { grid-template-columns: 1fr; } .sequence { grid-template-columns: repeat(4, 1fr); justify-items: stretch; } .sequence > span { width: auto; } }
  `];

  connectedCallback(): void { super.connectedCallback(); void this.boot(); }
  disconnectedCallback(): void { this.eventStream?.close(); super.disconnectedCallback(); }

  render() {
    return html`
      <main class="shell">
        <header>
          <div>
            <div class="brand"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>Powercalc Measure</div>
            <h1>Turn real watts into a precise profile.</h1>
            <p class="subtitle">Configure, validate, and monitor a light measurement without leaving Home Assistant.</p>
          </div>
          <div class="header-aside">
            <button class="settings-toggle" type="button" @click=${this.openSettings} ?disabled=${this.view === "loading" || this.view === "settings"}>Settings</button>
            <nav class="sequence" aria-label="Measurement steps">
              ${["setup", "review", "running", "result"].map((step, index) => html`<span class=${this.stepClass(index)}><span class="sr-only">${step}</span></span>`)}
            </nav>
          </div>
        </header>
        ${this.renderView()}
        <footer>Keep this app running while the selected light is being measured.</footer>
      </main>
    `;
  }

  private renderLoading() {
    return html`
      <section class="panel loading" aria-live="polite"><div><div class="pulse" aria-hidden="true"></div><p>${this.loadingMessage}</p>${this.errorMessage ? this.renderRetry() : nothing}</div></section>`;
  }

  private renderRetry() {
    return html`<p class="error" role="alert">${this.errorMessage}</p><button @click=${this.boot}>Retry</button>`;
  }

  private renderView() {
    if (this.view === "loading") return this.renderLoading();
    if (this.view === "settings") return html`
      <measure-settings-view .powers=${this.powers} .settings=${this.settings} .busy=${this.busy} .errorMessage=${this.errorMessage} @back=${this.closeSettings} @save=${this.saveSettings}></measure-settings-view>`;
    if (this.view === "review" && this.request && this.preflight) return html`
      <measure-preflight-view .request=${this.request} .preflight=${this.preflight} .busy=${this.busy} .errorMessage=${this.errorMessage} @back=${this.backToSetup} @start=${this.start}></measure-preflight-view>`;
    if (this.view === "running" && this.snapshot) return html`
      <measure-running-view .snapshot=${this.snapshot} .connected=${this.connectedToEvents} .logs=${this.logs} .busy=${this.busy} @cancel=${this.cancel}></measure-running-view>`;
    if (this.view === "result" && this.snapshot) return html`
      <measure-result-view .snapshot=${this.snapshot} .files=${this.files} .fileUrl=${(name: string) => this.api.fileUrl(name)} .busy=${this.busy} .errorMessage=${this.errorMessage} @new=${this.newMeasurement} @resume=${this.resume}></measure-result-view>`;
    return html`
      <measure-setup-view .capabilities=${this.capabilities} .lights=${this.lights} .powers=${this.powers} .voltages=${this.voltages} .initialRequest=${this.request} .defaultPowerEntityId=${this.settings?.default_power_entity_id ?? ""} .busy=${this.busy} .errorMessage=${this.errorMessage} @preflight=${this.runPreflight}></measure-setup-view>`;
  }

  private async boot(): Promise<void> {
    this.view = "loading"; this.errorMessage = "";
    try {
      const currentPromise = this.api.getCurrent().catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) return { state: "idle" } satisfies SessionSnapshot;
        throw error;
      });
      [this.capabilities, this.lights, this.powers, this.voltages, this.settings, this.snapshot] = await Promise.all([
        this.api.getCapabilities(), this.api.getEntities("light"), this.api.getEntities("power"), this.api.getEntities("voltage"), this.api.getSettings(), currentPromise,
      ]);
      this.request = this.snapshot.request;
      await this.routeSnapshot();
    } catch (error) { this.errorMessage = this.message(error); }
  }

  private async routeSnapshot(): Promise<void> {
    const state = this.snapshot?.state ?? "idle";
    if (["running", "cancelling", "validating", "ready"].includes(state)) { this.view = "running"; this.connectEvents(); return; }
    if (["completed", "failed", "cancelled", "resumable"].includes(state)) { this.view = "result"; await this.loadFiles(); return; }
    this.view = "setup";
  }

  private runPreflight(event: CustomEvent<MeasurementRequest>): void { void this.preflightRequest(event.detail); }
  private async preflightRequest(request: MeasurementRequest): Promise<void> {
    this.busy = true; this.errorMessage = ""; this.request = request;
    try { this.preflight = await this.api.preflight(request); this.view = "review"; }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private backToSetup(): void { this.errorMessage = ""; this.view = "setup"; }
  private start(): void { void this.startRequest(); }
  private async startRequest(): Promise<void> {
    if (!this.request) return;
    this.busy = true; this.errorMessage = "";
    try { this.snapshot = await this.api.start(this.request); this.view = "running"; this.connectEvents(); }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }

  private connectEvents(): void {
    this.eventStream?.close();
    this.eventStream = new SessionEventStream(this.api.eventsUrl(), (event) => this.consumeEvent(event),
      (connected) => { this.connectedToEvents = connected; }, () => { void this.refreshSnapshot(); });
    this.eventStream.connect();
  }

  private consumeEvent(event: SessionEvent): void {
    if (event.message && event.type === "log") this.logs = [...this.logs.slice(-39), event.message];
    if (event.snapshot) this.snapshot = event.snapshot;
    if (this.snapshot && this.isTerminal(this.snapshot.state)) void this.enterResult();
  }

  private async refreshSnapshot(): Promise<void> {
    try {
      this.snapshot = await this.api.getCurrent();
      if (this.isTerminal(this.snapshot.state)) await this.enterResult();
    }
    catch { this.connectedToEvents = false; }
  }

  private isTerminal(state: SessionSnapshot["state"]): boolean {
    return ["completed", "failed", "cancelled", "resumable"].includes(state);
  }

  private async enterResult(): Promise<void> {
    this.eventStream?.close();
    this.connectedToEvents = false;
    // If the user is on the settings view when a session finishes, don't yank them
    // away — send them to the result view only once they close settings.
    if (this.view === "settings") this.settingsReturnView = "result";
    else this.view = "result";
    await this.loadFiles();
  }
  private cancel(): void { void this.cancelRequest(); }
  private async cancelRequest(): Promise<void> {
    this.busy = true;
    try { this.snapshot = await this.api.cancel(); }
    catch (error) { this.logs = [...this.logs, `Cancellation failed: ${this.message(error)}`]; }
    finally { this.busy = false; }
  }
  private async loadFiles(): Promise<void> { try { this.files = await this.api.getFiles(); } catch { this.files = []; } }
  private newMeasurement(): void {
    this.eventStream?.close(); this.snapshot = { state: "idle" }; this.request = undefined; this.preflight = undefined;
    this.files = []; this.logs = []; this.errorMessage = ""; this.view = "setup";
  }
  private resume(): void { void this.resumeRequest(); }
  private async resumeRequest(): Promise<void> {
    this.busy = true; this.errorMessage = "";
    try { this.snapshot = await this.api.resume(); this.view = "running"; this.connectEvents(); }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private openSettings(): void {
    if (this.view === "loading" || this.view === "settings") return;
    this.settingsReturnView = this.view;
    this.errorMessage = ""; this.view = "settings";
  }
  private closeSettings(): void { this.errorMessage = ""; this.view = this.settingsReturnView; }
  private saveSettings(event: CustomEvent<AppSettings>): void { void this.saveSettingsRequest(event.detail); }
  private async saveSettingsRequest(settings: AppSettings): Promise<void> {
    this.busy = true; this.errorMessage = "";
    try { this.settings = await this.api.saveSettings(settings); this.view = this.settingsReturnView; }
    catch (error) { this.errorMessage = this.message(error); }
    finally { this.busy = false; }
  }
  private stepClass(index: number): string {
    const current = { loading: 0, setup: 0, review: 1, running: 2, result: 3, settings: 0 }[this.view];
    if (index === current) return "active";
    if (index < current) return "done";
    return "";
  }
  private message(error: unknown): string { return error instanceof Error ? error.message : "Something went wrong. Try again."; }
}

customElements.define("powercalc-measure-app", AppShell);
