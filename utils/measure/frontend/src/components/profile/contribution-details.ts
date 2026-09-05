import { html, nothing } from "lit";
import { customElement } from "lit/decorators.js";
import { words } from "../../utils/format";
import { ProfileFormSection } from "./form-section";

@customElement("measure-profile-contribution-details")
export class ProfileContributionDetails extends ProfileFormSection {
  render() {
    const context = Object.entries(this.draft.home_assistant).filter(([, value]) => value !== null && value !== "");
    return html`
      <fieldset class="metadata-group" ?disabled=${this.busy}>
        <legend>Contribution notes</legend>
        <div class="metadata-group-body">
          <p class="metadata-group-description">Optional context for reviewers; this is not added to model.json.</p>
          ${this.renderTextarea("notes", "Notes", this.draft.notes)}
        </div>
      </fieldset>
      ${context.length ? html`
        <details class="profile-details">
          <summary>Measurement context</summary>
          <div class="profile-details-body">
            <dl class="info-list" aria-label="Home Assistant measurement context">
              ${context.map(([label, value]) => html`<div><dt><span>Home Assistant ${words(label)}</span></dt><dd>${value}</dd></div>`)}
            </dl>
          </div>
        </details>` : nothing}`;
  }
}
