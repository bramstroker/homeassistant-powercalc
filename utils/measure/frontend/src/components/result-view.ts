import { LitElement, css, html, nothing } from "lit";
import type { SessionFile, SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";

export class ResultView extends LitElement {
  static readonly properties = {
    snapshot: { attribute: false },
    files: { attribute: false },
    fileUrl: { attribute: false },
    downloadAll: { attribute: false },
    busy: { type: Boolean },
    errorMessage: { type: String },
  };

  snapshot!: SessionSnapshot;
  files: SessionFile[] = [];
  fileUrl: (name: string) => string = () => "";
  downloadAll: () => void = () => {};
  busy = false;
  errorMessage = "";

  static readonly styles = [sharedStyles, css`
    .result-summary { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1rem; align-items: start; padding-bottom: 1.5rem; border-bottom: 1px solid var(--line); }
    .result-summary h2 { margin-bottom: 0.4rem; }
    .result-summary .muted { margin-bottom: 0; }
    .status-mark { display: grid; place-items: center; width: 48px; height: 48px; border: 1px solid var(--line); border-radius: 50%; color: var(--good); font: 700 1.3rem/1 ui-monospace, monospace; }
    .status-mark.failed { color: var(--danger); }
    .status-mark.cancelled, .status-mark.resumable { color: var(--signal); }
    .readout { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1px; overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: var(--line); margin-top: 1.5rem; }
    .metric { padding: 1rem; background: var(--field); }
    .metric span { display: block; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric strong { display: block; margin-top: 0.35rem; font: 700 1.4rem/1.1 "DIN Alternate", sans-serif; color: var(--signal-strong); }
    .files-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 1.5rem; }
    .files-header h3 { margin: 0; font-size: 1rem; }
    .download-all { min-height: 36px; padding: 0.45rem 0.75rem; border-radius: 999px; font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; }
    ul { list-style: none; margin: 0.65rem 0 0; padding: 0; border-top: 1px solid var(--line); }
    li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 1rem; padding: 0.8rem 0; border-bottom: 1px solid var(--line); }
    li span { overflow-wrap: anywhere; } li small { color: var(--muted); }
    a { color: var(--signal-strong); font-weight: 700; }
    @media (max-width: 520px) {
      .files-header { align-items: flex-start; flex-direction: column; }
      li { grid-template-columns: 1fr auto; }
      li small { grid-column: 1; grid-row: 2; }
    }
  `];

  render() {
    const state = this.snapshot.state;
    const error = typeof this.snapshot.error === "string" ? this.snapshot.error : this.snapshot.error?.message;
    return html`
      <section class="panel" aria-labelledby="result-title">
        <p class="eyebrow">04 / Result</p>
        <div class="result-summary">
          <div class="status-mark ${state}" aria-hidden="true">${this.statusMark(state)}</div>
          <div><h2 id="result-title">${this.resultTitle(state)}</h2><p class="muted">${this.description(state)}</p></div>
        </div>
        ${error ? html`<p class="notice error" role="alert">${error}</p>` : nothing}
        ${this.renderSummary()}
        ${this.files.length ? html`
          <div class="files-header">
            <h3>Generated files</h3>
            <button class="download-all" type="button" @click=${() => this.downloadAll()}>Download all</button>
          </div>
          <ul>${this.files.map((file) => html`
            <li><span>${file.name}</span><small>${this.size(file.size)}</small><a href=${this.fileUrl(file.name)} download>Download<span class="sr-only"> ${file.name}</span></a></li>
          `)}</ul>
        ` : this.summaryEntries().length ? nothing : html`<p class="notice">No downloadable files are available for this session.</p>`}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions">
          <button type="button" @click=${() => this.emit("new")}>New measurement</button>
          ${this.renderResume(state)}
        </div>
      </section>
    `;
  }

  private summaryEntries(): [string, string][] {
    return this.snapshot.summary ? Object.entries(this.snapshot.summary) : [];
  }

  private renderSummary() {
    const entries = this.summaryEntries();
    if (!entries.length) return nothing;
    return html`<div class="readout" aria-label="Measurement result">
      ${entries.map(([label, value]) => html`<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)}
    </div>`;
  }

  private renderResume(state: SessionSnapshot["state"]) {
    if (state !== "resumable" && state !== "cancelled") return nothing;
    return html`<button class="primary" type="button" @click=${() => this.emit("resume")} ?disabled=${this.busy}>${this.busy ? "Resuming…" : "Resume measurement"}</button>`;
  }

  private statusMark(state: SessionSnapshot["state"]): string {
    if (state === "completed") return "✓";
    if (state === "failed") return "!";
    return "↻";
  }

  private resultTitle(state: SessionSnapshot["state"]): string {
    if (state === "completed") return this.summaryEntries().length ? "Measurement complete" : "Profile captured";
    if (state === "failed") return "Measurement stopped with an error";
    if (state === "resumable") return "A measurement can be resumed";
    return "Measurement cancelled";
  }

  private description(state: SessionSnapshot["state"]): string {
    if (state === "completed") return this.summaryEntries().length ? "Here is the measured result." : "The complete output is ready to inspect or download.";
    if (state === "resumable") return "Compatible output was found. Continue from the last complete variation.";
    return "Any complete output rows have been kept safely.";
  }

  private size(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1_048_576).toFixed(1)} MB`;
  }

  private emit(name: "new" | "resume"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-result-view", ResultView);
