import type { SessionFile } from "../types";

export function hasModelArtifact(files: SessionFile[]): boolean {
  return files.some((file) => file.name.split("/").at(-1) === "model.json");
}
