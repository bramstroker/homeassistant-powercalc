import { css, html } from "lit";

/** Theme tokens live on the app shell and inherit through every nested shadow root. */
export const themeStyles = css`
  :host {
    --measure-ink: #eef2f7;
    --measure-muted: #93a1b5;
    --measure-canvas: #0d1119;
    --measure-surface: #151b24;
    --measure-surface-raised: #1e2632;
    --measure-well: #0a0e15;
    --measure-field: #111925;
    --measure-line: #2c3644;
    --measure-track: #2a3444;
    --measure-grid: #55647a;
    --measure-signal: #5488e8;
    --measure-signal-deep: #3f74d6;
    --measure-signal-strong: #93b5f4;
    --measure-on-signal: #ffffff;
    --measure-good: #61d4a3;
    --measure-warning: #f2b84b;
    --measure-danger: #ff7b72;
    --measure-color-scheme: dark;
  }

  :host([data-theme="light"]) {
    --measure-ink: #1b2634;
    --measure-muted: #586779;
    --measure-canvas: #f4f7fb;
    --measure-surface: #ffffff;
    --measure-surface-raised: #edf2f7;
    --measure-well: #e8eef5;
    --measure-field: #f8fafc;
    --measure-line: #c5cfda;
    --measure-track: #d6dee8;
    --measure-grid: #9aa8b8;
    --measure-signal: #326bc4;
    --measure-signal-deep: #2459a6;
    --measure-signal-strong: #174b91;
    --measure-on-signal: #ffffff;
    --measure-good: #147455;
    --measure-warning: #8a5b00;
    --measure-danger: #bc332d;
    --measure-color-scheme: light;
  }

  @media (prefers-color-scheme: light) {
    :host([data-theme="system"]) {
      --measure-ink: #1b2634;
      --measure-muted: #586779;
      --measure-canvas: #f4f7fb;
      --measure-surface: #ffffff;
      --measure-surface-raised: #edf2f7;
      --measure-well: #e8eef5;
      --measure-field: #f8fafc;
      --measure-line: #c5cfda;
      --measure-track: #d6dee8;
      --measure-grid: #9aa8b8;
      --measure-signal: #326bc4;
      --measure-signal-deep: #2459a6;
      --measure-signal-strong: #174b91;
      --measure-on-signal: #ffffff;
      --measure-good: #147455;
      --measure-warning: #8a5b00;
      --measure-danger: #bc332d;
      --measure-color-scheme: light;
    }
  }
`;

export const sharedStyles = css`
  :host {
    --ink: var(--measure-ink, #eef2f7);
    --muted: var(--measure-muted, #93a1b5);
    --canvas: var(--measure-canvas, #0d1119);
    --surface: var(--measure-surface, #151b24);
    --surface-raised: var(--measure-surface-raised, #1e2632);
    --well: var(--measure-well, #0a0e15);
    --field: var(--measure-field, #111925);
    --line: var(--measure-line, #2c3644);
    --track: var(--measure-track, #2a3444);
    --grid: var(--measure-grid, #55647a);
    --signal: var(--measure-signal, #5488e8);
    --signal-deep: var(--measure-signal-deep, #3f74d6);
    --signal-strong: var(--measure-signal-strong, #93b5f4);
    --on-signal: var(--measure-on-signal, #ffffff);
    --good: var(--measure-good, #61d4a3);
    --warning: var(--measure-warning, #f2b84b);
    --danger: var(--measure-danger, #ff7b72);
    --radius: 14px;
    color-scheme: var(--measure-color-scheme, dark);
    color: var(--ink);
    font-family: "Avenir Next", "Segoe UI", sans-serif;
  }

  *, *::before, *::after { box-sizing: border-box; }

  h1, h2, h3, p { margin-top: 0; }
  h1, h2, h3 {
    font-family: "DIN Alternate", "Avenir Next Condensed", sans-serif;
    letter-spacing: 0.015em;
  }

  button, input, select { font: inherit; }

  button {
    min-height: 44px;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 0.65rem 1rem;
    color: var(--ink);
    background: var(--surface-raised);
    font-weight: 650;
    cursor: pointer;
    transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
  }

  button:hover:not(:disabled) { border-color: var(--signal); transform: translateY(-1px); }
  button:active:not(:disabled) { transform: translateY(0); }
  button:disabled { opacity: 0.52; cursor: not-allowed; }
  button.primary { border-color: var(--signal-deep); background: var(--signal-deep); color: var(--on-signal); }
  button.primary:hover:not(:disabled) { border-color: var(--signal); background: var(--signal); }
  button.danger { border-color: color-mix(in srgb, var(--danger) 70%, var(--line)); color: var(--danger); }

  button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible {
    outline: 3px solid color-mix(in srgb, var(--signal) 60%, transparent);
    outline-offset: 3px;
  }

  .actions { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem; }
  .panel { background: color-mix(in srgb, var(--surface) 94%, transparent); border: 1px solid var(--line); border-radius: var(--radius); padding: clamp(1rem, 3vw, 1.5rem); }
  .eyebrow { margin-bottom: 0.45rem; color: var(--signal); font: 700 0.72rem/1.2 ui-monospace, monospace; letter-spacing: 0.15em; text-transform: uppercase; }
  .muted { color: var(--muted); }
  .error { color: var(--danger); }
  .notice { padding: 0.8rem 1rem; border-left: 3px solid var(--signal); background: color-mix(in srgb, var(--signal) 8%, transparent); }
  .notice.warning { border-left-color: var(--warning); background: color-mix(in srgb, var(--warning) 10%, transparent); color: var(--warning); }
  .notice.error { border-left-color: var(--danger); background: color-mix(in srgb, var(--danger) 9%, transparent); }
  .diagnostics-download { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 0.35rem 1rem; margin-top: 1.25rem; color: var(--muted); font-size: 0.78rem; }
  .diagnostics-download a { color: var(--signal-strong); font-weight: 700; white-space: nowrap; }
  /* Form controls. Every view that renders inputs shares this baseline. */
  label, fieldset { display: grid; gap: 0.4rem; min-width: 0; }
  label > span, legend, .field-label { color: var(--muted); font-size: 0.82rem; font-weight: 650; }
  fieldset { border: 0; padding: 0; margin: 0; }
  input, select, textarea {
    width: 100%; min-width: 0; max-width: 100%; min-height: 44px; border: 1px solid var(--line); border-radius: 9px;
    padding: 0.65rem 0.75rem; background: var(--field); color: var(--ink);
  }
  input::placeholder, textarea::placeholder {
    background: transparent;
    color: var(--muted);
    opacity: 0.75;
  }
  .check { display: flex; grid-template-columns: none; align-items: center; gap: 0.5rem; color: var(--ink); }
  .check input { width: auto; min-height: auto; accent-color: var(--signal); }
  .field-hint { color: var(--muted); font-size: 0.74rem; line-height: 1.4; }
  .field-hint.error, .required-marker { color: var(--danger); }
  input[aria-invalid="true"], textarea[aria-invalid="true"], select[aria-invalid="true"] { border-color: var(--danger); box-shadow: inset 0 0 0 1px var(--danger); }
  .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
  .context { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }

  @keyframes spin { to { transform: rotate(360deg); } }

  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

  @media (max-width: 640px) {
    .actions { flex-direction: column-reverse; }
    .actions button { width: 100%; }
    .grid { grid-template-columns: 1fr; }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
  }
`;

/** The diagnostics download offered at the foot of the running and result views. */
export const diagnosticsDownload = (url: string) => html`
  <div class="diagnostics-download">
    <span>Session snapshot and logs for issue reporting.</span>
    <a href=${url} download>Download diagnostics</a>
  </div>
`;
