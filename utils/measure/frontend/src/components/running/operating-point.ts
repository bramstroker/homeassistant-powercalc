import { LitElement, css, html, svg } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { OperatingPoint } from "../../types";

type StateChipIcon =
  | "battery"
  | "brightness"
  | "charging"
  | "color-temp"
  | "effect"
  | "fan-speed"
  | "hue"
  | "muted"
  | "not-charging"
  | "off"
  | "saturation"
  | "volume";

interface StateChip {
  label: string;
  icon: StateChipIcon;
}

@customElement("measure-operating-point")
export class OperatingPointView extends LitElement {
  @property({ attribute: false })
  point!: OperatingPoint;

  static readonly styles = css`
    :host { display: block; }
    .operating-point { position: relative; margin-top: 1.2rem; }
    .operating-point > span { display: block; margin-bottom: 0.55rem; color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .state-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; }
    .state-chip { display: inline-flex; align-items: center; gap: 0.38rem; padding: 0.38rem 0.65rem; border: 1px solid var(--line); border-radius: 999px; background: color-mix(in srgb, var(--signal) 8%, var(--well)); font: 650 0.78rem/1 ui-monospace, monospace; color: var(--ink); }
    .state-icon { width: 14px; height: 14px; flex: none; color: var(--signal-strong); }
  `;

  render() {
    const chips = this.chips(this.point);
    return html`
      <div class="operating-point" aria-live="polite">
        <span>Current measurement point</span>
        <div class="state-chips">
          ${chips.map((chip) => html`<span class="state-chip">${this.icon(chip.icon)}${chip.label}</span>`)}
        </div>
      </div>
    `;
  }

  private chips(point: OperatingPoint): StateChip[] {
    switch (point.type) {
      case "light":
        return this.lightChips(point);
      case "speaker":
        return [{ label: point.muted ? "Muted" : `Volume ${point.volume}%`, icon: point.muted ? "muted" : "volume" }];
      case "fan":
        return [{ label: point.on ? `Fan speed ${point.percentage}%` : "Off", icon: point.on ? "fan-speed" : "off" }];
      case "charging":
        return [
          { label: `Battery ${point.battery_level}%`, icon: "battery" },
          { label: point.charging ? "Charging" : "Not charging", icon: point.charging ? "charging" : "not-charging" },
        ];
    }
  }

  private lightChips(point: Extract<OperatingPoint, { type: "light" }>): StateChip[] {
    if (!point.on) return [{ label: "Off", icon: "off" }];
    const chips: StateChip[] = [];
    if (typeof point.brightness === "number") chips.push({ label: `Brightness ${Math.round(point.brightness / 255 * 100)}%`, icon: "brightness" });
    if (typeof point.color_temp_mired === "number") chips.push({ label: `Color temp ${Math.round(1_000_000 / point.color_temp_mired)} K`, icon: "color-temp" });
    if (typeof point.hue === "number") chips.push({ label: `Hue ${Math.round(point.hue / 65_535 * 360)}°`, icon: "hue" });
    if (typeof point.saturation === "number") chips.push({ label: `Saturation ${Math.round(point.saturation / 255 * 100)}%`, icon: "saturation" });
    if (point.effect) chips.push({ label: `Effect ${point.effect}`, icon: "effect" });
    return chips;
  }

  private icon(icon: StateChipIcon) {
    const content = {
      battery: svg`<rect x="2" y="4.25" width="11" height="7.5" rx="1.25"></rect><path d="M14 6.5v3"></path><path d="M4 6.5h5"></path>`,
      brightness: svg`<circle cx="8" cy="8" r="2.25"></circle><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.4 1.4M11.55 11.55l1.4 1.4M12.95 3.05l-1.4 1.4M4.45 11.55l-1.4 1.4"></path>`,
      charging: svg`<path d="m9.2 1.8-5 7h3.3l-.7 5.4 5-7H8.5l.7-5.4Z"></path>`,
      "color-temp": svg`<path d="M6.2 9.5V3.3a1.8 1.8 0 0 1 3.6 0v6.2a3 3 0 1 1-3.6 0Z"></path><path d="M8 5v6"></path>`,
      effect: svg`<path d="m8 1 .8 3.2L12 5l-3.2.8L8 9l-.8-3.2L4 5l3.2-.8L8 1Z"></path><path d="m12.5 9 .45 1.55 1.55.45-1.55.45L12.5 13l-.45-1.55-1.55-.45 1.55-.45L12.5 9Z"></path>`,
      "fan-speed": svg`<circle cx="8" cy="8" r="1.15" fill="currentColor" stroke="none"></circle><path d="M8.5 6.9c.3-2.6 1.35-4.2 2.7-3.7 1.5.55 1.25 2.9-.15 4.25"></path><path d="M8.7 8.95c2.4 1.05 3.25 2.8 2.1 3.65-1.3.95-3.2-.45-3.7-2.3"></path><path d="M6.8 8.15c-2.1 1.55-4.05 1.4-4.25-.05-.2-1.6 1.95-2.55 3.8-2.05"></path>`,
      hue: svg`<circle cx="8" cy="8" r="5.5"></circle><path d="M8 2.5v3M13.5 8h-3M8 13.5v-3M2.5 8h3"></path>`,
      muted: svg`<path d="M2 6h2.5L8 3v10l-3.5-3H2V6Z"></path><path d="m11 6 3 4m0-4-3 4"></path>`,
      "not-charging": svg`<path d="m9.2 1.8-3 4.2M5 8H4.2l.55-.78M7.5 8h4.3l-2.25 3.15M8.8 12.2l-2 2 .28-2.2"></path><path d="m2 2 12 12"></path>`,
      off: svg`<path d="M8 1.5v6"></path><path d="M4.2 3.7a5.5 5.5 0 1 0 7.6 0"></path>`,
      saturation: svg`<path d="M8 1.5s4.5 5 4.5 8.2a4.5 4.5 0 1 1-9 0C3.5 6.5 8 1.5 8 1.5Z"></path><path d="M5.7 10.2c.25 1.1 1.05 1.65 2 1.8"></path>`,
      volume: svg`<path d="M2 6h2.5L8 3v10l-3.5-3H2V6Z"></path><path d="M10.5 5.5a3.5 3.5 0 0 1 0 5M12.5 3.5a6.2 6.2 0 0 1 0 9"></path>`,
    } satisfies Record<StateChipIcon, unknown>;
    return html`
      <svg class="state-icon" data-state-icon=${icon} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
        ${content[icon]}
      </svg>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "measure-operating-point": OperatingPointView;
  }
}
