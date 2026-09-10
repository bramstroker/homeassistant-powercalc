export interface ShellyDiscoveryDevice {
  id: string;
  name: string;
  model: string | null;
  generation: number | null;
  ip_address: string;
  supported: boolean;
  reason: string | null;
  auth_required: boolean;
}

export interface ShellyDiscoveryResponse {
  devices: ShellyDiscoveryDevice[];
  available: boolean;
  message: string | null;
}

export type DiagnosticStatus = "good" | "warning" | "poor" | "unsupported";
export type PrecisionStatus = "good" | "poor" | "unsupported";

export interface PowerMeterDiagnostic {
  success: boolean;
  power?: number | null;
  supports_voltage?: boolean | null;
  status: DiagnosticStatus;
  precision_decimals?: number | null;
  max_report_interval_seconds?: number | null;
  reports_observed: number;
  duration_seconds: number;
  precision_status: PrecisionStatus;
  update_interval_status: DiagnosticStatus;
  messages: string[];
  message?: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
  help_url?: string | null;
  help_label?: string | null;
}

export interface ErrorHelp {
  url: string;
  label: string;
}
