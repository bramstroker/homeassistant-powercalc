import { LitElement, css, html, nothing, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { createRef, ref } from "lit/directives/ref.js";
import { sharedStyles } from "../../styles";

@customElement("measure-session-log")
export class SessionLog extends LitElement {
  @property({ attribute: false })
  logs: string[] = [];

  @property({ attribute: false })
  warnings: string[] = [];

  @state()
  open = false;

  private readonly container = createRef<HTMLDivElement>();

  static readonly styles = [sharedStyles, css`
    :host { display: inline-flex; }
    .log-toggle { display: inline-flex; align-items: center; gap: 0.55rem; min-height: 44px; padding: 0.55rem 0.75rem 0.55rem 0.9rem; border-radius: 999px; font: 700 0.78rem/1 ui-monospace, monospace; color: var(--ink); background: var(--surface-raised); }
    .log-count { display: inline-grid; place-items: center; min-width: 1.6rem; min-height: 1.6rem; padding: 0 0.4rem; border-radius: 999px; color: var(--signal-strong); background: color-mix(in srgb, var(--signal) 16%, var(--well)); font-size: 0.7rem; }
    .log-overlay { position: fixed; top: 0; right: 0; bottom: 0; z-index: 60; display: flex; flex-direction: column; width: min(400px, 92vw); padding: 1rem; background: color-mix(in srgb, var(--surface) 96%, transparent); border-left: 1px solid var(--line); box-shadow: -18px 0 40px rgba(0, 0, 0, 0.4); backdrop-filter: blur(2px); }
    .log-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.7rem; }
    .log-head span { color: var(--muted); font: 700 0.72rem/1 ui-monospace, monospace; letter-spacing: 0.12em; text-transform: uppercase; }
    .log-head button { min-height: 32px; padding: 0.3rem 0.6rem; }
    .log { flex: 1; overflow: auto; padding: 0.9rem; border: 1px solid var(--line); border-radius: 10px; background: var(--well); font: 0.8rem/1.6 ui-monospace, monospace; color: var(--muted); }
    .log p { margin: 0; }
    .log p.warning { color: var(--warning); }
  `];

  protected updated(changedProperties: PropertyValues<this>): void {
    if ((changedProperties.has("logs") || changedProperties.has("open")) && this.open && this.logs.length) {
      const container = this.container.value;
      if (container) container.scrollTop = container.scrollHeight;
    }
  }

  render() {
    if (!this.logs.length) return nothing;
    return html`
      <button class="log-toggle" type="button" @click=${this.toggle} aria-expanded=${this.open}>
        View log <span class="log-count">${this.logs.length}</span>
      </button>
      ${this.open ? html`
        <aside class="log-overlay" aria-label="Measurement log">
          <div class="log-head">
            <span>Measurement log</span>
            <button type="button" @click=${this.toggle} aria-label="Close log">Close ✕</button>
          </div>
          <div ${ref(this.container)} class="log" aria-live="polite">
            ${this.logs.map((log) => html`<p class=${this.warnings.includes(log) ? "warning" : ""}>${log}</p>`)}
          </div>
        </aside>
      ` : nothing}
    `;
  }

  private toggle(): void {
    this.open = !this.open;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "measure-session-log": SessionLog;
  }
}
