import { LitElement, css, html, nothing } from "lit";
import type { AppSettings, EntityDescriptor } from "../types";
import { sharedStyles } from "../styles";

export class SettingsView extends LitElement {
  static readonly properties = {
    powers: { attribute: false },
    settings: { attribute: false },
    busy: { type: Boolean },
    errorMessage: { type: String },
  };

  powers: EntityDescriptor[] = [];
  settings?: AppSettings;
  busy = false;
  errorMessage = "";

  static readonly styles = [sharedStyles, css`
    form { display: grid; gap: 1rem; margin-top: 1rem; }
    label { display: grid; gap: 0.4rem; }
    label > span { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
    select {
      width: 100%; min-height: 44px; border: 1px solid var(--line); border-radius: 9px;
      padding: 0.65rem 0.75rem; background: var(--field); color: var(--ink);
    }
    .context { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
  `];

  render() {
    const selected = this.settings?.default_power_entity_id ?? "";
    return html`
      <section class="panel" aria-labelledby="settings-title">
        <div class="context">
          <div>
            <p class="eyebrow">Settings</p>
            <h2 id="settings-title">Measurement defaults</h2>
          </div>
        </div>
        <p class="muted">Defaults are applied to every new measurement. You can still change them per session.</p>
        <form @submit=${this.submit}>
          <label>
            <span>Default power sensor</span>
            <select name="default_power_entity_id">
              <option value="">No default</option>
              ${this.powers.map((entity) => html`<option value=${entity.entity_id} ?selected=${entity.entity_id === selected}>${entity.name} · ${entity.entity_id}</option>`)}
            </select>
          </label>
          ${this.errorMessage ? html`<p class="notice error" role="alert">${this.errorMessage}</p>` : nothing}
          <div class="actions">
            <button type="button" @click=${() => this.emit("back")}>Back</button>
            <button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? "Saving…" : "Save settings"}</button>
          </div>
        </form>
      </section>
    `;
  }

  private submit(event: SubmitEvent): void {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const value = data.get("default_power_entity_id");
    const settings: AppSettings = { default_power_entity_id: typeof value === "string" && value ? value : null };
    this.dispatchEvent(new CustomEvent<AppSettings>("save", { detail: settings, bubbles: true, composed: true }));
  }

  private emit(name: "back"): void {
    this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true }));
  }
}

customElements.define("measure-settings-view", SettingsView);
