import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { emit } from "../../events";

@customElement("measure-setup-developer-options")
export class SetupDeveloperOptions extends LitElement {
  @property({ type: Boolean }) developerMode = false;
  @property({ type: Boolean }) fastTestMode = false;
  @property({ type: Boolean }) hasController = false;
  @property({ type: Boolean }) dummyController = false;

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  render() {
    if (!(this.developerMode && this.hasController) && !this.fastTestMode) return nothing;
    return html`<details class="developer-options">
      <summary>Developer options</summary>
      <div class="developer-content">
        ${this.developerMode && this.hasController ? this.renderDummyController() : nothing}
        ${this.fastTestMode
          ? html`<p class="notice"><strong>Fast test mode is enabled.</strong> Dummy light, fan, speaker and charging runs use minimal waits and measurement points. Their output is for app testing only.</p>`
          : nothing}
      </div>
    </details>`;
  }

  private renderDummyController() {
    return html`
      <div class="dummy-controller">
        <label class="check toggle-pill">
          <input
            type="checkbox"
            name="use_dummy_controller"
            .checked=${this.dummyController}
            @change=${this.dummyControllerChanged}
          />
          Use virtual device (developer)
        </label>
        ${this.dummyController
          ? html`<p class="muted">No real device is controlled during this measurement. Use it only to test the app itself.</p>`
          : nothing}
      </div>
    `;
  }

  private readonly dummyControllerChanged = (event: Event): void => {
    emit<boolean>(this, "dummy-controller-change", (event.currentTarget as HTMLInputElement).checked);
  };
}
