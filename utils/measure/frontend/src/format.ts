/** Presentation helpers shared by the views, so the same value never reads two ways. */

/** A file or storage size, in the largest unit that keeps the number readable. */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

/** A snake_case identifier as prose: `awaiting_confirmation` becomes `Awaiting confirmation`. */
export function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

/** The same, without capitalising — for labels that sit inside a sentence. */
export function words(value: string): string {
  return value.replaceAll("_", " ");
}

/** A duration in whole units, rounded up so an estimate never reads as already finished. */
export function duration(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)} sec`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  return hours ? `${hours} hr ${minutes} min` : `${minutes} min`;
}

/** A remaining time, in the coarser shape the running view shows while a measurement is in flight. */
export function remaining(seconds?: number | null): string {
  if (seconds == null) return "Calculating";
  const minutes = Math.ceil(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
}

export function timestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function calibrationDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString();
}

export function resistance(ohms: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(ohms);
}
