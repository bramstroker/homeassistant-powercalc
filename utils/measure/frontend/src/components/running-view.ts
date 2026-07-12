import { LitElement, css, html, nothing } from "lit";
import type { SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";

export class RunningView extends LitElement {
  static properties = {
    snapshot: { attribute: false },
    connected: { type: Boolean },
    logs: { attribute: false },
    busy: { type: Boolean },
  };

  snapshot!: SessionSnapshot;
  connected = false;
  logs: string[] = [];
  busy = false;

  static styles = [sharedStyles, css`
    .instrument { position: relative; overflow: hidden; background: #0d1215; border: 1px solid var(--line); border-radius: 16px; padding: clamp(1.2rem, 4vw, 2rem); }
    .instrument::before { content: ""; position: absolute; inset: 0; opacity: 0.24; pointer-events: none; background: repeating-linear-gradient(90deg, transparent 0, transparent calc(10% - 1px), #607078 10%); }
    .topline { position: relative; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
    .connection { display: inline-flex; align-items: center; gap: 0.45rem; color: var(--muted); font-size: 0.82rem; }
    .connection::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); }
    .connection.connected::before { background: var(--good); box-shadow: 0 0 0 4px color-mix(in srgb, var(--good) 16%, transparent); }
    .value { position: relative; margin: 2rem 0 1.2rem; font: 700 clamp(3rem, 12vw, 7rem)/0.85 "DIN Alternate", sans-serif; letter-spacing: -0.06em; color: var(--signal-strong); }
    .value small { font-size: 0.18em; letter-spacing: 0.08em; color: var(--muted); }
    progress { position: relative; display: block; width: 100%; height: 8px; border: 0; border-radius: 99px; overflow: hidden; appearance: none; }
    progress::-webkit-progress-bar { background: #303a40; } progress::-webkit-progress-value { background: var(--signal); } progress::-moz-progress-bar { background: var(--signal); }
    .metrics { position: relative; display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1.2rem; }
    .metric span { display: block; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric strong { display: block; margin-top: 0.25rem; font: 600 1rem/1.3 ui-monospace, monospace; }
    .log { max-height: 9rem; overflow: auto; margin-top: 1rem; padding: 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: #0d1215; font: 0.8rem/1.6 ui-monospace, monospace; color: var(--muted); }
    .log p { margin: 0; }
    @media (max-width: 640px) { .metrics { grid-template-columns: 1fr 1fr; } .topline { align-items: flex-start; flex-direction: column; } }
  `];

  render() {
    const progress = this.snapshot.progress ?? { completed: 0, total: 0 };
    const percent = progress.percent ?? (progress.total ? progress.completed / progress.total * 100 : 0);
    return html`
      <section class="panel" aria-labelledby="running-title">
        <p class="eyebrow">03 / Measurement</p>
        <h2 id="running-title">${this.snapshot.state === "cancelling" ? "Stopping safely" : "Sampling in progress"}</h2>
        <div class="instrument">
          <div class="topline">
            <span class="muted">${this.snapshot.phase ?? "Preparing measurement"}</span>
            <span class="connection ${this.connected ? "connected" : ""}" role="status">${this.connected ? "Live" : "Reconnecting"}</span>
          </div>
          <div class="value" aria-label="${Math.round(percent)} percent complete">${Math.round(percent)}<small>%</small></div>
          <progress max="100" .value=${percent}>${Math.round(percent)}%</progress>
          <div class="metrics">
            <div class="metric"><span>Mode</span><strong>${this.snapshot.mode ?? "—"}</strong></div>
            <div class="metric"><span>Variation</span><strong>${progress.completed} / ${progress.total}</strong></div>
            <div class="metric"><span>Remaining</span><strong>${this.remaining(progress.estimated_remaining_seconds)}</strong></div>
          </div>
        </div>
        ${this.snapshot.warnings?.length ? html`<div class="notice" role="status">${this.snapshot.warnings.at(-1)}</div>` : nothing}
        ${this.logs.length ? html`<div class="log" aria-label="Recent measurement log" aria-live="polite">${this.logs.map((log) => html`<p>${log}</p>`)}</div>` : nothing}
        <div class="actions"><button class="danger" type="button" @click=${this.cancel} ?disabled=${this.busy || this.snapshot.state === "cancelling"}>${this.snapshot.state === "cancelling" ? "Cancelling…" : "Cancel measurement"}</button></div>
      </section>
    `;
  }

  private remaining(seconds?: number | null): string {
    if (seconds == null) return "Calculating";
    const minutes = Math.ceil(seconds / 60);
    return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
  }

  private cancel(): void {
    this.dispatchEvent(new CustomEvent("cancel", { bubbles: true, composed: true }));
  }
}

customElements.define("measure-running-view", RunningView);
