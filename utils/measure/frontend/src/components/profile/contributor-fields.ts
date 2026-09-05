import { html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ContributionAuthState } from "../../types";
import { ProfileFormSection } from "./form-section";

@customElement("measure-profile-contributor-fields")
export class ProfileContributorFields extends ProfileFormSection {
  @property({ attribute: false }) contributionAuth?: ContributionAuthState;

  render() {
    return html`<fieldset class="metadata-group" ?disabled=${this.busy}>
      <legend>Contributor</legend>
      <div class="metadata-group-body">
        <p class="metadata-group-description">These details are prefilled from your profile settings and credited in model.json.</p>
        <div class="contribution-grid contributor-grid">
          ${this.renderInput("contributor", "Name", this.draft.contributor)}
          ${this.renderInput(
            "contributor_github",
            "GitHub username",
            this.draft.contributor_github ?? this.contributionAuth?.identity?.login ?? "",
          )}
          ${this.renderInput("contributor_email", "Email", this.draft.contributor_email ?? "", { required: false })}
        </div>
      </div>
    </fieldset>`;
  }
}
