import { LitElement, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ContributionDraftFile, ContributionPreview } from "../../types";
import { fileSize } from "../../format";

@customElement("measure-profile-prepared-preview")
export class ProfilePreparedPreview extends LitElement {
  @property({ attribute: false }) preview!: ContributionPreview;

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  render() {
    const files = this.preview.files.map((file) => formatPreparedFile(file)).join("\n");
    const model = this.preview.model_json
      ?? this.preview.files.find((file) => file.path.endsWith("model.json"))?.rendered_json
      ?? {};
    return html`
      ${this.preview.warnings.map((warning) => html`<p class="notice warning preparation-warning">${warning}</p>`)}
      <details class="profile-details prepared-preview">
        <summary>Prepared files (${this.preview.files.length})</summary>
        <div class="profile-details-body">
          <div class="preview-block"><span>Files</span><pre>${files}</pre></div>
          <div class="preview-block"><span>Generated model.json</span><pre>${JSON.stringify(model, null, 2)}</pre></div>
        </div>
      </details>`;
  }
}

function formatPreparedFile(file: ContributionDraftFile): string {
  return file.size === undefined ? file.path : `${file.path} (${fileSize(file.size)})`;
}
