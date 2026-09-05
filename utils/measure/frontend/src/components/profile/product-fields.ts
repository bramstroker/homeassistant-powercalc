import { html } from "lit";
import { customElement, property } from "lit/decorators.js";
import { ProfileFormSection } from "./form-section";
import "../shared/combobox";

@customElement("measure-profile-product-fields")
export class ProfileProductFields extends ProfileFormSection {
  @property({ attribute: false }) manufacturers: string[] = [];

  render() {
    const manufacturer = this.fieldValue("manufacturer_name", this.draft.manufacturer_name);
    return html`<fieldset class="metadata-group" ?disabled=${this.busy}>
      <legend>Product</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">Identity and manufacturer details used to place and discover this profile.</p>
        <div class="contribution-grid">
          <div class="field-stack">
            <measure-combobox
              name="manufacturer_name"
              label="Manufacturer"
              .error=${this.fieldError("manufacturer_name")}
              ?disabled=${this.busy}
              .value=${manufacturer}
              .options=${this.manufacturers.map((name) => ({ value: name, label: name }))}
              placeholder="Search or enter a manufacturer"
              hint="Choose an existing manufacturer or enter a new one."
              required
              allowCustom
            >
              <input slot="value" type="hidden" name="manufacturer_name" .value=${manufacturer} />
            </measure-combobox>
          </div>
          ${this.renderInput("model_id", "Model ID", this.draft.model_id)}
          ${this.renderInput("product_name", "Product name", this.draft.product_name, {
            hint: "Use the marketed name without repeating the manufacturer, e.g. “Hue White Ambiance GU10”.",
          })}
          ${this.renderInput("product_url", "Manufacturer product URL", this.draft.product_url ?? "", {
            required: false,
            placeholder: "https://…",
          })}
          ${this.renderInput("aliases", "Model aliases", (this.draft.aliases ?? []).join(", "), {
            required: false,
            placeholder: "Comma separated",
          })}
          ${this.renderInput("gtins", "GTIN / barcodes", (this.draft.gtins ?? []).join(", "), {
            required: false,
            placeholder: "Comma separated",
          })}
        </div>
      </div>
    </fieldset>`;
  }
}
