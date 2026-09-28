import { svg } from "lit";

const ICONS: Record<string, ReturnType<typeof svg>> = {
  air_purifier: svg`<rect x="5" y="3" width="14" height="18" rx="2"/><circle cx="12" cy="10" r="3"/><path d="M8 17h8"/>`,
  camera: svg`<path d="M4 7h3l2-2h6l2 2h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13" r="3"/>`,
  cover: svg`<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M5 9h14M5 13h14M5 17h14"/>`,
  fan: svg`<circle cx="12" cy="12" r="2"/><path d="M12 10c-2-5 0-8 3-7 2 1 1 4-1 7M14 12c5-2 8 0 7 3-1 2-4 1-7-1M12 14c2 5 0 8-3 7-2-1-1-4 1-7M10 12c-5 2-8 0-7-3 1-2 4-1 7 1"/>`,
  generic_iot: svg`<rect x="7" y="7" width="10" height="10" rx="1"/><path d="M10 10h4v4h-4zM10 3v4m4-4v4m-4 10v4m4-4v4M3 10h4m-4 4h4m10-4h4m-4 4h4"/>`,
  heating: svg`<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 5v14m4-14v14m4-14v14M6 21v-2m12 2v-2"/>`,
  humidifier: svg`<path d="M12 3c-3 4-7 8-7 12a7 7 0 0 0 14 0c0-4-4-8-7-12Z"/><path d="M8 15a4 4 0 0 0 4 4"/>`,
  light: svg`<path d="M9 18h6m-5 3h4m-5-5c0-2-4-4-4-8a7 7 0 0 1 14 0c0 4-4 6-4 8Z"/>`,
  network: svg`<circle cx="12" cy="5" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="18" r="2"/><path d="m11 7-5 9m7-9 5 9M7 18h10"/>`,
  power_meter: svg`<path d="m13 2-9 11h7l-1 9 10-12h-7l0-8Z"/>`,
  printer: svg`<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 15h12v6H6zM18 12h1"/>`,
  set_top_box: svg`<rect x="3" y="7" width="18" height="11" rx="2"/><path d="M7 14h5m4 0h1M7 4h10"/>`,
  smart_dimmer: svg`<path d="M6 3v18m12-18v18M3 8h6v4H3zm12 5h6v4h-6z"/>`,
  smart_speaker: svg`<rect x="6" y="3" width="12" height="18" rx="3"/><circle cx="12" cy="14" r="4"/><path d="M10 7h4"/>`,
  television: svg`<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8m-4-3v3"/>`,
  ups: svg`<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M10 7h4m-2 4-2 3h4l-2 3"/>`,
  vacuum_robot: svg`<circle cx="12" cy="12" r="9"/><path d="M7 9h10M9 15h6M12 3v3"/>`,
  water_heater: svg`<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M12 8c-2 3-3 4-3 6a3 3 0 0 0 6 0c0-2-1-3-3-6Z"/>`,
  free_measurement: svg`<path d="M4 20V4m0 16h16M7 16l4-4 3 2 5-7"/>`,
};

export function deviceIcon(deviceId: string) {
  const icon = ICONS[deviceId] ?? svg`<path d="M8 3v6m8-6v6M6 9h12v3a6 6 0 0 1-12 0V9Zm6 9v3"/>`;
  return svg`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icon}</svg>`;
}
