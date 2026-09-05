import { LitElement, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Capabilities, MeasureDefinition, MeasureParameter, MeasureParameterName, MeasurementRequest } from "../../types";
import { emit } from "../../events";
import { gatedParameters } from "../../measure-definition";
import { numberField } from "../shared/fields";

export interface ParameterChange {
  name: MeasureParameterName;
  value: string;
}

@customElement("measure-setup-tuning-section")
export class SetupTuningSection extends LitElement {
  @property({ attribute: false }) capabilities?: Capabilities;
  @property({ attribute: false }) definition!: MeasureDefinition;
  @property({ attribute: false }) definitions: MeasureDefinition[] = [];
  @property({ attribute: false }) request?: MeasurementRequest;
  @property({ attribute: false }) values: Partial<Record<MeasureParameterName, string>> = {};
  @property({ attribute: false }) activeParameters: ReadonlySet<string> = new Set();

  protected createRenderRoot(): HTMLElement | DocumentFragment {
    return this;
  }

  render() {
    if (!this.capabilities) return nothing;
    const gated = gatedParameters(this.definition);
    const shown = this.definition.parameters.filter(
      (parameter) => !gated.has(parameter.name) || this.activeParameters.has(parameter.name),
    );
    return html`<details>
      <summary>Advanced timing & quality</summary>
      <div class="grid">
        ${shown.map((parameter, index) => html`
          ${parameter.group && parameter.group !== shown[index - 1]?.group
            ? html`<p class="advanced-heading">${parameter.group}</p>`
            : nothing}
          ${this.renderParameter(parameter)}
        `)}
      </div>
    </details>`;
  }

  private renderParameter(parameter: MeasureParameter) {
    const gate = parameter.requires_multiple;
    const { min, max } = this.capabilities?.limits?.[parameter.name] ?? {};
    return numberField(parameter.name, parameter.label, this.parameterValue(parameter.name), {
      min,
      max,
      step: parameter.step,
      hint: parameter.hint,
      disabled: gate ? Number(this.parameterValue(gate)) <= 1 : false,
      onInput: this.gatesAnother(parameter.name) ? this.parameterChanged : null,
    });
  }

  private parameterValue(name: MeasureParameterName): string {
    const stored = this.request?.parameters[name] ?? this.capabilities?.defaults[name];
    return this.values[name] ?? String(stored ?? "");
  }

  private gatesAnother(name: MeasureParameterName): boolean {
    return this.definitions.some((definition) => definition.parameters.some((parameter) => parameter.requires_multiple === name));
  }

  private readonly parameterChanged = (event: Event): void => {
    const input = event.currentTarget as HTMLInputElement;
    emit<ParameterChange>(this, "parameter-change", { name: input.name as MeasureParameterName, value: input.value });
  };
}
