import type { ContributionPreviewRequest } from "./types";

export const metadataLabels: Record<string, string> = {
  manufacturer_name: "Manufacturer", model_id: "Model ID", product_name: "Product name",
  contributor: "Contributor name", contributor_github: "GitHub username", contributor_email: "Email",
  product_url: "Manufacturer product URL", aliases: "Model aliases", gtins: "GTIN / barcodes",
  mains_voltage: "Nominal mains voltage",
  measure_device: "Measurement device", measure_device_firmware: "Device firmware",
  measure_description: "Measurement description", notes: "Notes", device_specs: "Device specifications",
};

// Fast feedback for editable metadata. The server remains authoritative and also
// validates the complete generated model against the library's current schema.
export function validateMetadata(values: ContributionPreviewRequest): Record<string, string> {
  const errors: Record<string, string> = {};
  validateRequiredMetadata(values, errors);
  validateMainsVoltage(values, errors);
  const limits: Partial<Record<keyof ContributionPreviewRequest, number>> = {
    manufacturer_name: 200, model_id: 120, product_name: 200, contributor: 200,
    contributor_github: 100, contributor_email: 200, product_url: 2000,
    measure_device: 200, measure_device_firmware: 200, measure_description: 2000, notes: 2000,
  };
  for (const [name, limit] of Object.entries(limits)) {
    const value = values[name as keyof ContributionPreviewRequest];
    if (typeof value === "string" && value.length > limit) errors[name] = `Use ${limit} characters or fewer.`;
  }
  if (values.model_id && !/^[A-Za-z0-9][A-Za-z0-9 ._()+-]*$/.test(values.model_id)) {
    errors.model_id = "Start with a letter or number. Use only letters, numbers, spaces, dots, underscores, parentheses, + or -.";
  }
  if (values.product_url && !values.product_url.startsWith("https://")) errors.product_url = "Enter a URL starting with https://.";
  if (values.gtins?.some((value) => !/^(?:\d{8}|\d{12,14})$/.test(value))) {
    errors.gtins = "Enter barcodes of 8, 12, 13 or 14 digits, separated by commas.";
  }
  if (values.contributor_email && !validEmail(values.contributor_email)) {
    errors.contributor_email = "Enter a valid email address, for example name@example.com.";
  }
  const normalizeWords = (value: string) => value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const manufacturer = normalizeWords(values.manufacturer_name);
  const product = normalizeWords(values.product_name);
  if (manufacturer && (product === manufacturer || product.startsWith(`${manufacturer} `))) {
    errors.product_name = "Leave out the manufacturer; enter only the marketed model name.";
  }
  return errors;
}

function validateRequiredMetadata(values: ContributionPreviewRequest, errors: Record<string, string>): void {
  for (const name of ["manufacturer_name", "model_id", "product_name", "contributor", "contributor_github", "measure_device"] as const) {
    if (!values[name]?.trim()) errors[name] = `Enter ${metadataLabels[name]!.toLowerCase()}.`;
  }
}

function validateMainsVoltage(values: ContributionPreviewRequest, errors: Record<string, string>): void {
  if (values.mains_voltage === undefined || values.mains_voltage === null) {
    errors.mains_voltage = "Select the nominal mains voltage.";
  } else if (values.mains_voltage !== 120 && values.mains_voltage !== 230) {
    errors.mains_voltage = "Select either 120 V or 230 V.";
  }
}

function validEmail(value: string): boolean {
  const parts = value.split("@");
  if (/\s/.test(value) || parts.length !== 2) return false;
  const local = parts[0] ?? "";
  const domain = parts[1] ?? "";
  const dot = domain.lastIndexOf(".");
  return Boolean(local && dot > 0 && dot < domain.length - 1);
}
