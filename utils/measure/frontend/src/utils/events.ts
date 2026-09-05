/**
 * Every view talks to the shell the same way: a composed, bubbling `CustomEvent` that crosses the
 * shadow boundary. Going through one helper keeps that contract in a single place.
 */
export function emit<T = undefined>(host: EventTarget, name: string, detail?: T): void {
  host.dispatchEvent(new CustomEvent<T | undefined>(name, { detail, bubbles: true, composed: true }));
}
