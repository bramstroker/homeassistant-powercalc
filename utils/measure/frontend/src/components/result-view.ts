import { LitElement, css, html, nothing } from "lit";
import type { SessionFile, SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";

export class ResultView extends LitElement {
  static readonly properties = {
    snapshot: { attribute: false },
    files: { attribute: false },
    fileUrl: { attribute: false },
    busy: { type: Boolean },
    errorMessage: { type: String },
  };

  snapshot!: SessionSnapshot;
  files: SessionFile[] = [];
  fileUrl: (name: string) => string = () => "";
  busy = false;
  errorMessage = "";

  static readonly styles = [sharedStyles, css`
    .status-mark { display: grid; place-items: center; width: 54px; height: 54px; margin-bottom: 1rem; border: 1px solid var(--line); border-radius: 50%; color: var(--good); font: 700 1.5rem/1 ui-monospace, monospace; }
    .status-mark.failed { color: var(--danger); }
    .status-mark.cancelled, .status-mark.resumable { color: var(--signal); }
    ul { list-style: none; margin: 1rem 0 0; padding: 0; border-top: 1px solid var(--line); }
    li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 1rem; padding: 0.8rem 0; border-bottom: 1px solid var(--line); }
    li span { overflow-wrap: anywhere; } li small { color: var(--muted); }
    a { color: var(--signal-strong); font-weight: 700; }
    @media (max-width: 520px) { li { grid-template-columns: 1fr auto; } li small { grid-column: 1; grid-row: 2; } }
  `];

  render() {
    const state = this.snapshot.state;
    const error = typeof this.snapshot.error === "string" ? this.snapshot.error : this.snapshot.error?.message;
    return html`
      <section class="panel" aria-labelledby="result-title">
        <p class="eyebrow">04 / Result</p>
        <div class="status-mark ${state}" aria-hidden="true">${state === "completed" ? "✓" : state === "failed" ? "!" : "↻"}</div>
        <h2 id="result-title">${this.resultTitle(state)}</h2>
        <p class="muted">${this.description(state)}</p>
        ${error ? html`<p class="notice error" role="alert">${error}</p>` : nothing}
        ${this.files.length ? html`
          <h3>Generated files</h3>
          <ul>${this.files.map((file) => html`
            <li><span>${file.name}</span><small>${this.size(file.size)}</small><a href=${this.fileUrl(file.name)} download>Download<span class="sr-only"> ${file.name}</span></a></li>
          `)}</ul>
        ` : html`<p class="notice">No downloadable files are available for this session.</p>`}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        <div class="actions">
          <button type="button" @click=${() => this.emit("new")}>New measurement</button>
          ${state === "resumable" || state === "cancelled" ? html`<button class="primary" type="button" @click=${() => this.emit("resume")} ?disabled=${this.busy}>${this.busy ? "Resuming…" : "Resume measurement"}</button>` : nothing}
        </div>
      </section>
    `;
  }

  private resultTitle(state: SessionSnapshot["state"]): string {
    if (state === "completed") return "Profile captured";
    if (state === "failed") return "Measurement stopped with an error";
    if (state === "resumable") return "A measurement can be resumed";
    return "Measurement cancelled";
  }

  private description(state: SessionSnapshot["state"]): string {
    if (state === "completed") return "The complete output is ready to inspect or download.";
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
