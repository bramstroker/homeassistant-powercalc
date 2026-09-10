import { html, nothing } from "lit";
import type { ErrorHelp } from "../../types";

/** Render help metadata supplied explicitly by the API. */
export function errorHelpLink(help?: ErrorHelp) {
  return help
    ? html` <a href=${help.url} target="_blank" rel="noopener noreferrer">${help.label}</a>`
    : nothing;
}
