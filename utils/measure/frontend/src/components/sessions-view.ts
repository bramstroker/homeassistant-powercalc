import { LitElement, css, html, nothing, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { SessionSummary } from "../types";
import { emit } from "../events";
import { fileSize, humanize, timestamp } from "../format";
import { sharedStyles } from "../styles";

@customElement("measure-sessions-view")
export class SessionsView extends LitElement {
  static readonly styles = [sharedStyles, css`
    .heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; }
    .heading h2 { margin: 0.15rem 0 0.35rem; }
    .heading button, .empty button { display: inline-flex; align-items: center; justify-content: center; gap: 0.45rem; }
    .sessions { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); gap: 0.8rem; align-items: stretch; }
    article { display: flex; flex-direction: column; min-width: 0; padding: 0.9rem; border: 1px solid var(--line); border-radius: 12px; background: var(--well); }
    article.active { border-color: var(--signal); box-shadow: inset 3px 0 0 var(--signal); }
    .session-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
    h3 { margin: 0; font-size: 1rem; overflow-wrap: anywhere; }
    .state { display: inline-flex; padding: 0.3rem 0.55rem; border-radius: 999px; background: var(--surface-raised); color: var(--muted); font: 700 0.68rem/1 ui-monospace, monospace; text-transform: uppercase; }
    .state.running, .state.awaiting_confirmation { color: var(--signal-strong); }
    .state.completed { color: var(--good); }
    .state.failed { color: var(--danger); }
    dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.65rem 0.8rem; margin: 0.85rem 0; }
    dt { color: var(--muted); font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
    dd { margin: 0.15rem 0 0; font-size: 0.88rem; overflow-wrap: anywhere; }
    progress { width: 100%; height: 6px; margin-top: auto; accent-color: var(--signal); }
    .actions { justify-content: flex-start; gap: 0.4rem; margin-top: 0.75rem; }
    .actions button, .actions .action-button { display: inline-flex; align-items: center; justify-content: center; gap: 0.35rem; min-height: 34px; padding: 0.4rem 0.65rem; font-size: 0.78rem; }
    .actions .action-button { border: 1px solid var(--line); border-radius: 10px; color: var(--ink); background: var(--surface-raised); font-weight: 650; text-decoration: none; transition: transform 150ms ease, border-color 150ms ease, background 150ms ease; }
    .actions .action-button:hover { border-color: var(--signal); transform: translateY(-1px); }
    .tooltip-trigger { position: relative; display: inline-flex; }
    .tooltip-content {
      position: absolute;
      z-index: 10;
      bottom: calc(100% + 0.55rem);
      left: 50%;
      width: max-content;
      max-width: min(16rem, calc(100vw - 2rem));
      padding: 0.5rem 0.65rem;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface-raised);
      box-shadow: 0 8px 24px rgb(0 0 0 / 35%);
      color: var(--ink);
      font-size: 0.74rem;
      font-weight: 500;
      line-height: 1.35;
      text-align: center;
      pointer-events: none;
      opacity: 0;
      visibility: hidden;
      transform: translate(-50%, 0.2rem);
      transition: opacity 80ms ease, transform 80ms ease, visibility 0s linear 80ms;
    }
    .tooltip-content::after {
      content: "";
      position: absolute;
      top: 100%;
      left: 50%;
      width: 0.5rem;
      height: 0.5rem;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      background: var(--surface-raised);
      transform: translate(-50%, -50%) rotate(45deg);
    }
    .tooltip-trigger:hover .tooltip-content,
    .tooltip-trigger:focus-within .tooltip-content {
      opacity: 1;
      visibility: visible;
      transform: translate(-50%, 0);
      transition-delay: 0s;
    }
    .icon { width: 1rem; height: 1rem; flex: none; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
    .danger { color: var(--danger); }
    .empty { padding: 2rem; text-align: center; border: 1px dashed var(--line); border-radius: 12px; color: var(--muted); }
    @media (max-width: 720px) { .heading { flex-direction: column; } }
    @media (max-width: 640px) { .actions .action-button, .actions .tooltip-trigger { width: 100%; } }
  `];

  @property({ attribute: false })
  sessions: SessionSummary[] = [];

  @property({ type: Boolean })
  busy = false;

  @property({ type: String })
  errorMessage = "";

  @property({ attribute: false })
  diagnosticsUrl: (sessionId: string) => string = () => "";

  @state()
  private pendingDelete?: string;

  render() {
    const active = this.sessions.some((session) => session.active);
    return html`
      <section class="panel" aria-labelledby="sessions-title">
        <div class="heading">
          <div><p class="eyebrow">Measurement sessions</p><h2 id="sessions-title">Your measurements</h2><p class="muted">Resume interrupted work or inspect previous results.</p></div>
          <button class="primary" type="button" ?disabled=${this.busy || active} @click=${() => this.emit("new")}>${this.icon("new")}<span>New measurement</span></button>
        </div>
        ${active ? html`<p class="notice">Finish or cancel the active session before starting another measurement.</p>` : nothing}
        ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
        ${this.sessions.length ? html`<div class="sessions">${this.sessions.map((session) => this.renderSession(session))}</div>` : html`
          <div class="empty"><p>No measurement sessions yet.</p><button type="button" @click=${() => this.emit("new")}>${this.icon("new")}<span>Create your first measurement</span></button></div>
        `}
      </section>
    `;
  }

  private renderSession(session: SessionSummary) {
    const measureAgainTooltipId = `measure-again-tooltip-${session.session_id}`;
    return html`<article class=${session.active ? "active" : ""}>
      <div class="session-head">
        <div><h3>${session.product_name || session.model_id}</h3><small class="muted">${session.model_id} · ${humanize(session.measure_type)}</small></div>
        <span class="state ${session.state}">${humanize(session.state)}</span>
      </div>
      <dl>
        <div><dt>Updated</dt><dd>${timestamp(session.updated_at)}</dd></div>
        <div><dt>Measurement device</dt><dd>${session.measure_device || "—"}</dd></div>
        <div><dt>Files</dt><dd>${session.file_count}</dd></div>
        <div><dt>Storage</dt><dd>${fileSize(session.size)}</dd></div>
      </dl>
      ${session.total ? html`<progress max=${session.total} value=${session.completed}>${session.percent}%</progress>` : nothing}
      <div class="actions">
        <button type="button" ?disabled=${this.busy} @click=${() => this.emit("open", session.session_id)}>${this.icon(session.active ? "monitor" : "open")}<span>${session.active ? "Monitor" : "Open"}</span></button>
        ${session.can_resume ? html`<button type="button" ?disabled=${this.busy || this.sessions.some((item) => item.active)} @click=${() => this.emit("resume", session.session_id)}>${this.icon("resume")}<span>Resume</span></button>` : nothing}
        <span class="tooltip-trigger">
          <button type="button" aria-describedby=${measureAgainTooltipId} ?disabled=${this.busy} @click=${() => this.emit("duplicate", session.session_id)}>${this.icon("duplicate")}<span>Measure again</span></button>
          <span class="tooltip-content" id=${measureAgainTooltipId} role="tooltip">Start a new measurement using these settings</span>
        </span>
        <a class="action-button" href=${this.diagnosticsUrl(session.session_id)} download>${this.icon("diagnostics")}<span>Diagnostics</span></a>
        ${this.pendingDelete === session.session_id ? html`
          <button class="danger" type="button" ?disabled=${this.busy} @click=${() => this.confirmDelete(session.session_id)}>${this.icon("delete")}<span>Confirm delete</span></button>
          <button type="button" @click=${() => { this.pendingDelete = undefined; }}>${this.icon("keep")}<span>Keep</span></button>
        ` : html`<button class="danger" type="button" ?disabled=${this.busy || session.active} @click=${() => { this.pendingDelete = session.session_id; }}>${this.icon("delete")}<span>Delete</span></button>`}
      </div>
    </article>`;
  }

  private icon(name: "new" | "open" | "monitor" | "resume" | "duplicate" | "diagnostics" | "delete" | "keep") {
    const path = {
      new: svg`<path d="M8 3v10M3 8h10"/>`,
      open: svg`<path d="M2.5 8s2-3.5 5.5-3.5S13.5 8 13.5 8s-2 3.5-5.5 3.5S2.5 8 2.5 8Z"/><circle cx="8" cy="8" r="1.5"/>`,
      monitor: svg`<path d="M2.5 8h2l1.2-3 2.2 6 1.7-4 1 1h2.9"/>`,
      resume: svg`<path d="m5 3.5 7 4.5-7 4.5Z"/>`,
      duplicate: svg`<rect x="5" y="3" width="8" height="9" rx="1"/><path d="M3 5v7a1 1 0 0 0 1 1h6"/>`,
      diagnostics: svg`<path d="M8 2.5v7m-2.5-2L8 10l2.5-2.5M3 13h10"/>`,
      delete: svg`<path d="M3 4.5h10M6 4.5v-2h4v2m2 0-.6 9H4.6l-.6-9M6.5 7v4m3-4v4"/>`,
      keep: svg`<path d="m4 4 8 8m0-8-8 8"/>`,
    }[name];
    return svg`<svg class="icon" viewBox="0 0 16 16" aria-hidden="true">${path}</svg>`;
  }

  private confirmDelete(sessionId: string): void {
    this.pendingDelete = undefined;
    this.emit("delete", sessionId);
  }

  private emit(name: "new" | "open" | "resume" | "duplicate" | "delete", detail?: string): void {
    emit(this, name, detail);
  }
}
