import type { PrimitiveValue } from "./measurement";

export interface ContributionIdentity { login: string; }

export interface ContributionAuthState {
  connected: boolean;
  device_flow_available?: boolean;
  identity?: ContributionIdentity | null;
  method?: "device" | "token" | null;
  scopes?: string[];
  permissions_verified?: boolean;
}

export interface ContributionDeviceFlow {
  flow_id: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete?: string | null;
  expires_in: number;
  interval: number;
}

export interface ContributionAuthDeviceStatus {
  status: "pending" | "slow_down" | "authorized" | "expired" | "denied";
  auth?: ContributionAuthState | null;
  message?: string | null;
  retry_after?: number | null;
}

export interface ContributionTokenRequest { token: string; }

export interface ContributionDraftFile {
  path: string;
  size?: number;
  content?: string | null;
  rendered_json?: unknown;
}

export interface ContributionDraft {
  eligible: boolean;
  reason?: string | null;
  repository: string;
  fork_repository?: string | null;
  base_branch: string;
  base_sha?: string | null;
  manufacturer_name: string;
  manufacturer_directory: string;
  manufacturer_library_url?: string | null;
  model_id: string;
  product_name: string;
  contributor: string;
  contributor_github?: string;
  contributor_email?: string;
  aliases?: string[];
  gtins?: string[];
  product_url?: string;
  mains_voltage?: number | null;
  voltage_range?: { min: number; max: number } | null;
  device_specs?: Record<string, unknown> | null;
  device_type?: string;
  measure_device?: string;
  measure_device_firmware?: string;
  measure_description?: string;
  device_info: Record<string, PrimitiveValue>;
  home_assistant: Record<string, PrimitiveValue>;
  notes: string;
  files: ContributionDraftFile[];
  model_json?: unknown;
  commit_message: string;
  pr_title: string;
  pr_body: string;
  branch_name: string;
  job_id?: string | null;
}

/** Unparsed, edited controls: preserve intermediate text and multi-select values across steps. */
export type ContributionFormValues = Record<string, string | string[]>;

export interface ContributionPreviewRequest {
  manufacturer_name: string;
  model_id: string;
  product_name: string;
  contributor: string;
  contributor_github?: string;
  contributor_email?: string;
  aliases?: string[];
  gtins?: string[];
  product_url?: string;
  mains_voltage?: number | null;
  device_specs?: Record<string, unknown> | null;
  measure_device?: string;
  measure_device_firmware?: string;
  measure_description?: string;
  notes: string;
}

export interface ContributionPreview extends ContributionDraft { warnings: string[]; }
export interface ContributionSubmitRequest extends ContributionPreviewRequest { confirmed: true; }

export interface ContributionResult {
  status: "success" | "failed" | "pending";
  message?: string | null;
  repository?: string | null;
  branch_name?: string | null;
  pull_request_url?: string | null;
}

export type ContributionState = "idle" | "preview_ready" | "submitting" | "submitted" | "failed";

export interface ContributionStatus {
  state: ContributionState;
  session_id?: string | null;
  preview?: ContributionPreview | null;
  submission_url?: string | null;
  message?: string | null;
  error?: string | null;
  updated_at?: string | null;
}
