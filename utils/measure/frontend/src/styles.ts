import { css } from "lit";

export const sharedStyles = css`
  :host {
    --ink: #eef2f7;
    --muted: #93a1b5;
    --canvas: #0d1119;
    --surface: #151b24;
    --surface-raised: #1e2632;
    --well: #0a0e15;
    --field: #0f1520;
    --line: #2c3644;
    --track: #2a3444;
    --grid: #55647a;
    --signal: #5488e8;
    --signal-deep: #3f74d6;
    --signal-strong: #93b5f4;
    --on-signal: #ffffff;
    --good: #61d4a3;
    --danger: #ff7b72;
    --radius: 14px;
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

  button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible {
    outline: 3px solid color-mix(in srgb, var(--signal) 60%, transparent);
    outline-offset: 3px;
  }

  .actions { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem; }
  .panel { background: color-mix(in srgb, var(--surface) 94%, transparent); border: 1px solid var(--line); border-radius: var(--radius); padding: clamp(1rem, 3vw, 1.5rem); }
  .eyebrow { margin-bottom: 0.45rem; color: var(--signal); font: 700 0.72rem/1.2 ui-monospace, monospace; letter-spacing: 0.15em; text-transform: uppercase; }
  .muted { color: var(--muted); }
  .error { color: var(--danger); }
  .notice { padding: 0.8rem 1rem; border-left: 3px solid var(--signal); background: color-mix(in srgb, var(--signal) 8%, transparent); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

  @media (max-width: 640px) {
    .actions { flex-direction: column-reverse; }
    .actions button { width: 100%; }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
  }
`;
